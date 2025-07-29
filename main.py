from fastapi import FastAPI, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os, traceback, requests
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

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
def kakao_error_response(message: str):
    return JSONResponse(content={
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"[에러 발생]\n{message}"
                    }
                }
            ]
        }
    })

# ✅ 공통 처리
async def handle_skill_request(model: str, user_input: str):
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type": "application/json"
    }

    gpt_payload = {
        "model": model,
        "input": user_input
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses", headers=headers, json=gpt_payload
        )
        gpt_result = response.json()
        reply_text = gpt_result["output"][0]["content"][0]["text"]
    except Exception:
        print("❌ GPT 처리 중 오류:", traceback.format_exc())
        return kakao_error_response("GPT 응답 처리 중 오류가 발생했습니다.")

    return JSONResponse(content={
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": reply_text
                    }
                }
            ]
        }
    })

# ✅ Swagger 테스트 가능하게 설정
@app.post("/skill-ui-test", tags=["Skill API (Swagger + Kakao 지원)"])
async def skill_ui_test(data: UIRequestBody = Body(...)):
    print("📥 받은 JSON:", data.model, data.input)
    return await handle_skill_request(data.model, data.input)

@app.post("/skill-ui-test-raw", tags=["Kakao Chatbot Webhook"])
async def skill_ui_test_raw(data: KakaoRequestBody = Body(...)):
    try:
        print("📥 받은 JSON (RAW):", data)

        model = "gpt-4.1-nano"
        user_input = None

        if data.action and data.action.params:
            # model = data.action.params.model
            user_input = data.action.params.input
        elif data.action and data.action.detailParams:
            detail = data.action.detailParams
            # model = detail.get("model", {}).get("value")
            user_input = detail.get("input", {}).get("value")
        else:
            # model = data.model
            user_input = data.input

        # if not model or not user_input:
        if not user_input:    
            return kakao_error_response("모델이나 입력값이 누락되었습니다.")

        return await handle_skill_request(model, user_input)

    except Exception:
        print("❌ skill-ui-test-raw 처리 중 오류:", traceback.format_exc())
        return kakao_error_response("요청 파싱 중 오류가 발생했습니다.")

from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        print("❌ JSON 파싱 오류! 입력된 바디:", body.decode("utf-8"))
    except Exception:
        print("❌ JSON 파싱 오류! 바디 디코딩 실패")

    return kakao_error_response("입력 JSON이 잘못되었어요. 올바른 형식으로 다시 보내주세요.")
