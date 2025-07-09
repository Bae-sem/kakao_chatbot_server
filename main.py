from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

class KakaoRequestParams(BaseModel):
    model: str
    input: str

@app.post("/skill-ui-test")
async def skill_ui_test(params: KakaoRequestParams):
    gpt_payload = {
        "model": params.model,
        "input": params.input
    }

    api_key = os.getenv("OPENAI_API_KEY")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post("https://api.openai.com/v1/responses", headers=headers, json=gpt_payload)
    gpt_result = response.json()

    try:
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
