from fastapi import FastAPI, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request as StarletteRequest
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

import os, traceback, requests, json, redis
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# ✅ Redis 연결
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
rdb = redis.Redis.from_url(REDIS_URL, decode_responses=True)
예약_URL = "https://www.naver.com"
# ✅ GPT 초기 역할 설정
initial_role = f"""
너는 '글로리수학' 학원의 AI 상담 챗봇이야. 사용자는 모두 학부모님이므로 응답 시 항상 '학부모님'이라는 호칭을 사용해.  
모든 첫 응답은 반드시 다음과 같이 시작해:  
'안녕하세요, 글로리수학입니다.'

## 응답 스타일 가이드
- 문장은 20자 안팎으로 정중하지만 간결하게 말해.
- 필요할 경우만 이모지 사용 (😊 ✍️ 등), 너무 자주 사용하지 마.
- 핵심 정보를 명확히 안내하고, 예약이 필요한 경우에는 링크를 직접 출력해: https://www.naver.com (너무 예약 링크를 남발하면 너무 장사꾼 같으니 필요할때나 사용자가 원할때 맞게 해줘).
- 질문이 불명확하거나 애매하면 정중하게 다시 물어봐. 예: "조금 더 구체적으로 알려주실 수 있을까요, 학부모님?"

## 학원 기본 정보
- 위치: 서울시 강남구 선릉로62길 32-2, 2층 (대치동)
- 역: 한티역(분당선) 3번 출구 도보 약 6~7분
- 주차: 불가, 대중교통 이용 권장
- 상담 예약: 네이버 예약 시스템 이용 {예약_URL}
- 상담/입학 테스트: 1시간 30분 소요, 평일 16:00~20:00 시작 / 토요일 10:00

## 수업 구성
- 형태: 1:1 또는 소수정예 개별 수업 (무학년제)
- 수업 시간: 1회 3시간
- 강사 1명당 최대 6명
- 수업 전 레벨 테스트 필수
- 주요 수업 유형:
  - 대형학원 입반 테스트 대비
  - 대형학원 백업 수업 (진도 보강, 오답 정리)
  - 개념 선행 및 심화 학습
  - 중등 내신 대비 수업
  - 1:1 수업
  - 실전 모의고사 수업

## 수업 요금
- 초등: 시간당 43,000원
- 중등: 시간당 45,000원
- 고등: 시간당 50,000원

## 상담 봇의 역할
- 인텐트 블록에 매칭되지 않는 질문에도 자연스럽게 안내하거나 유도해.
- 질문이 상담 예약, 수업 방식, 요금, 수업 시간, 위치 등에 관한 것이라면 적절히 안내해주고 예약_URL로 유도해.
- 모든 예약 URL은 현재 {예약_URL} 으로 할거야 임시로!
- 예시처럼 정중하게 이어줘:

예시 1:  
"안녕하세요, 글로리수학입니다. 😊  
학부모님, 입학 전 테스트는 예약 URL 에서 신청하실 수 있어요.
예약 URL: {예약_URL}

예시 2:  
"안녕하세요, 글로리수학입니다.  
저희 학원은 무학년제 1:1 수업으로 운영됩니다. 자세한 상담은  예약_URL 에서 도와드릴게요.
예약 URL: {예약_URL}

예시 3:  
"안녕하세요, 글로리수학입니다.  
수업은 1회 3시간이며, 초등 기준 시간당 43,000원입니다.  
자세한 안내는 상담 후 결정됩니다.
예약 URL: {예약_URL}"

답변이 곤란한 주제인 경우는 다음처럼 정중하게 말해:  
"죄송합니다, 학부모님. 수업/상담과 관련된 질문으로 도와드릴 수 있어요. 조금 더 구체적으로 알려주실 수 있을까요?"\

그래도 학습과 관련된 이야기라면 (예를들어 방정식이 무슨 뜻이야?) 친절히 답변해줘도 좋을거 같아! -> 너무 이상하지만 않으면 왠만하면 다 답변을 해줘 (일방적인 모욕이나 혼잣말 같은 경우)

항상 정중하고 신뢰감을 주는 톤으로 말해.
"""

MAX_USERS = 300

# ✅ 입력 스키마
class UIRequestBody(BaseModel):
    model: str
    input: str

class KakaoActionParams(BaseModel):
    model: str | None = None
    input: str | None = None

class KakaoAction(BaseModel):
    params: KakaoActionParams | None = None
    detailParams: dict | None = None

class KakaoRequestBody(BaseModel):
    action: KakaoAction | None = None
    model: str | None = None
    input: str | None = None

# ✅ 카카오 응답 템플릿

def kakao_simple_response(text: str):
    return JSONResponse(content={
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": text}}
            ]
        }
    })

def kakao_error_response(message: str):
    return kakao_simple_response(f"[에러 발생]\n{message}")

# ✅ 공통 처리 (대화 저장 포함)
async def handle_skill_request(model: str, user_input: str, user_id: str):
    try:
        # ✅ 사용자 순서 관리 (최대 300명)
        rdb.lrem("user_list", 0, user_id)
        rdb.rpush("user_list", user_id)
        if rdb.llen("user_list") > MAX_USERS:
            oldest_user = rdb.lpop("user_list")
            rdb.delete(f"user:{oldest_user}:history")

        # 🔄 최근 10개만 불러오기
        raw_history = rdb.lrange(f"user:{user_id}:history", -10, -1)
        message_history = [json.loads(msg) for msg in raw_history]

        # ✅ 항상 system 메시지는 맨 앞에 고정
        final_messages = [{"role": "system", "content": initial_role}]
        final_messages.extend(message_history)
        final_messages.append({"role": "user", "content": user_input})

        print("📤 GPT에 보낼 메시지:", json.dumps(final_messages, indent=2, ensure_ascii=False))

        # GPT 요청
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }
        gpt_payload = {
            "model": model,
            "messages": final_messages
        }

        response = requests.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=gpt_payload
        )

        if response.status_code != 200:
            print("❌ GPT 응답 오류:", response.status_code, response.text)
            return kakao_error_response("GPT 응답 중 오류가 발생했습니다.")

        gpt_result = response.json()
        reply_text = gpt_result["choices"][0]["message"]["content"]

        # 🔐 대화 저장 (질문 + 답변)
        rdb.rpush(f"user:{user_id}:history", json.dumps({"role": "user", "content": user_input}))
        rdb.rpush(f"user:{user_id}:history", json.dumps({"role": "assistant", "content": reply_text}))

        # ✅ 최대 저장 개수 제한 (앞에서 자르기)
        while rdb.llen(f"user:{user_id}:history") > 100:
            rdb.lpop(f"user:{user_id}:history")

        return kakao_simple_response(reply_text)

    except Exception:
        print("❌ 처리 중 예외 발생:", traceback.format_exc())
        return kakao_error_response("서버 처리 중 예기치 못한 오류가 발생했습니다.")

# ✅ Swagger 테스트 가능
@app.post("/skill-ui-test", tags=["Skill API (Swagger + Kakao 지원)"])
async def skill_ui_test(data: UIRequestBody = Body(...)):
    print("📥 받은 JSON:", data.model, data.input)
    return await handle_skill_request(data.model, data.input, user_id="test-user")

# ✅ 카카오 웹훅
@app.post("/skill-ui-test-raw", tags=["Kakao Chatbot Webhook"])
async def skill_ui_test_raw(request: Request):
    try:
        body = await request.body()
        print("📥 원본 JSON:", body.decode("utf-8"))
        data = KakaoRequestBody.parse_raw(body)

        model = "gpt-4.1-nano"
        user_input = None

        if data.action and data.action.params and data.action.params.input:
            user_input = data.action.params.input
        elif data.action and data.action.detailParams:
            user_input = data.action.detailParams.get("input", {}).get("value")

        if not user_input:
            parsed = json.loads(body)
            user_input = parsed.get("userRequest", {}).get("utterance")
        else:
            parsed = json.loads(body)

        user_id = parsed.get("userRequest", {}).get("user", {}).get("id")

        if not user_input or not user_id:
            return kakao_error_response("입력값 또는 사용자 ID가 누락되었습니다.")

        return await handle_skill_request(model, user_input, user_id)

    except Exception:
        print("❌ skill-ui-test-raw 처리 중 오류:", traceback.format_exc())
        return kakao_error_response("요청 파싱 중 오류가 발생했습니다.")

# ✅ 예외 핸들러
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: StarletteRequest, exc: RequestValidationError):
    try:
        body = await request.body()
        print("❌ JSON 파싱 오류! 입력된 바디:", body.decode("utf-8"))
    except Exception:
        print("❌ JSON 파싱 오류! 바디 디코딩 실패")

    return kakao_error_response("입력 JSON이 잘못되었어요. 올바른 형식으로 다시 보내주세요.")