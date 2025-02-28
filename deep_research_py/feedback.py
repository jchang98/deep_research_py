from typing import List, Optional
import openai
import ollama
import json
from .prompt import system_prompt
from .common.logging import log_error, log_event
from .ai.providers import generate_completions
from .common.token_cunsumption import (
    parse_ollama_token_consume,
    parse_openai_token_consume,
)
from deep_research_py.utils import get_service
from pydantic import BaseModel
import re

class FeedbackResponse(BaseModel):
    questions: List[str]


async def generate_feedback(
    query: str,
    client: Optional[openai.OpenAI | ollama.Client],
    model: str,
    max_feedbacks: int = 5,
) -> List[str]:
    """Generates follow-up questions to clarify research direction."""

    prompt = f"""Analyze the research topic: "{query}" and identify any ambiguous or unclear aspects that need clarification. Generate up to {max_feedbacks} clarifying questions that will help better understand the user's research intent.
Requirements for the follow-up questions:
- Focus on ambiguous or undefined aspects in the original query.
- Please prompt the user  to help narrow down the user's intent.
- If the original query is sufficiently clear and comprehensive, you may return an empty string.
- Return the response as raw text, not in JSON format."""

    response = await generate_completions(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt()},
            {
                "role": "user",
                "content": prompt,
            },
        ],
        # format=FeedbackResponse.model_json_schema(),
        # format={"type": "json_object"},
    )

    # Parse the JSON response
    try:
        if get_service() == "ollama":
            result = json.loads(response.message.content)
            parse_ollama_token_consume("generate_feedback", response)
        else:
            # OpenAI compatible API
            # json格式兜底
            result = response.choices[0].message.content
            # try:
            #     json.loads(json_response) # 为正常json
            # except:
            #     json_response = re.findall(r"```(?:json)?\s*(.*?)\s*```", json_response, re.DOTALL)[0]

            # result = json.loads(json_response)
            
            # result = json.loads(response.choices[0].message.content.strip().strip("```json").strip("```"))
            parse_openai_token_consume("generate_feedback", response)

        log_event(
            f"Generated {max_feedbacks} feedback follow-up questions for query: {query}"
        )
        log_event(f"Got feedback follow-up questions: {result}")
        return [result]
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        log_error(f"Failed to parse JSON response for query: {query}")
        return []
