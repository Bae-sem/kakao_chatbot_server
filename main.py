from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests

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

    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }

    response = requests.post("https://api.openai.com/v1/responses", headers=headers, json=gpt_payload)
    gpt_result = response.json()
    # print(gpt_result)
    reply_text = gpt_result["output"][0]["content"][0]["text"]

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
