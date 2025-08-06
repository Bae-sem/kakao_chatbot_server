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

# ✅ GPT 초기 역할 설정
initial_role = "너는 한국어 선생님이야"
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