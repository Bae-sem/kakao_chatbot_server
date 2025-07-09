from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ✅ Swagger용 모델 (심플한 요청용)
class SkillRequest(BaseModel):
    model: str
    input: str

# ✅ 오픈빌더용 모델 (실제 JSON 구조 대응)
class SkillRawRequest(BaseModel):
    action: dict | None = None
    model: str | None = None
    input: str | None = None

# ✅ 공통 처리 함수
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
        reply_text = "GPT 응답을 불러오는 데 실패했습니다."

    kakao_response = {
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
    }

    return JSONResponse(content=kakao_response)

# ✅ /skill-ui-test - Swagger 테스트용 기본 엔드포인트
@app.post("/skill-ui-test", tags=["Skill API (Swagger + Kakao 지원)"])
async def skill_ui_test(data: SkillRequest):
    return await handle_skill_request(data.model, data.input)

# ✅ /skill-ui-test-raw - Swagger 테스트 가능한 카카오 구조용 엔드포인트
@app.post("/skill-ui-test-raw", tags=["Kakao Chatbot Webhook"])
async def skill_ui_test_raw(data: SkillRawRequest):
    model = None
    user_input = None

    try:
        model = data.action.get("params", {}).get("model")
        user_input = data.action.get("params", {}).get("input")
    except:
        try:
            model = data.action.get("detailParams", {}).get("model", {}).get("value")
            user_input = data.action.get("detailParams", {}).get("input", {}).get("value")
        except:
            model = data.model
            user_input = data.input

    if not model or not user_input:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing model or input"}
        )

    return await handle_skill_request(model, user_input)
