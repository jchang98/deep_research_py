from typing import List, Dict, TypedDict, Optional
import asyncio
import os
import openai
from firecrawl import FirecrawlApp
from .ai.providers import trim_prompt, generate_completions
from .prompt import system_prompt
from .common.logging import log_event, log_error
from .common.token_cunsumption import (
    parse_ollama_token_consume,
    parse_openai_token_consume,
)
from .utils import get_service
import json
from pydantic import BaseModel
import requests
import httpx
from datetime import datetime
import re

class SearchResponse(TypedDict):
    data: List[Dict[str, str]]


class ResearchResult(TypedDict):
    learnings: List[str]
    visited_urls: List[str]


class SerpQuery(BaseModel):
    query: str
    research_goal: str


def bing_search(query):
    url = 'https://tgenerator.aicubes.cn/iwc-index-search-engine/search_engine/v1/search'
    
    params = {
        'query': query,
        # 'se': 'BAIDU',
        'se': 'BING',
        'limit': 5,
        'user_id': 'test',
        'app_id': 'test',
        'trace_id': 'test',
        'with_content': True
    }

    header = {
        'X-Arsenal-Auth': 'arsenal-tools'
    }
    try:
        response_dic = requests.post(url, data=params, headers=header)
        # async with httpx.AsyncClient() as client:
        #     response_dic = await client.post(url, data=params, headers=header)

        if response_dic.status_code == 200:
            response =  json.loads(response_dic.text)['data']

            # 替换为serapi googlesearch的格式

            organic_results_lst = []
            for idx, t in enumerate(response):
                position = idx +1
                title = t['title'] if t['title'] else ""
                link = t['url']
                snippet = t['summary'] if t['summary'] else ""
                date = t['publish_time'] if t['publish_time'] else ""
                source = t['data_source'] if t['data_source'] else ""
                content = t['content'] if t['content'] else ""


                if date:
                    dt_object = datetime.fromtimestamp(date)
                    formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
                    date = formatted_time
                    

                organic_results_lst.append({
                    "position": position,
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                    "date": date,
                    "source": source,
                    "content": content
                })
            
            # res = {
            #     "search_parameters": response_dic.json()['header'],
            #     "organic_results": organic_results_lst
            # }

            return organic_results_lst

        else:
            print(f"搜索失败，状态码：{response.status_code}")
            return []
    except Exception as e:
        print(f"请求发生错误：{str(e)}")
        return []  # 出现异常时也返回空列表

class Firecrawl:
    """Simple wrapper for Firecrawl SDK."""

    def __init__(self, api_key: str = "", api_url: Optional[str] = None):
        self.app = FirecrawlApp(api_key=api_key, api_url=api_url)

    async def search(
        self, query: str, timeout: int = 15000, limit: int = 5
    ) -> SearchResponse:
        """Search using Firecrawl SDK in a thread pool to keep it async."""
        try:
            # Run the synchronous SDK call in a thread pool
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: bing_search(
                    query=query,
                ),
            )
            # response = await bing_search(query)

            # Handle the response format from the SDK
            if isinstance(response, dict) and "data" in response:
                # Response is already in the right format
                return response
            elif isinstance(response, dict) and "success" in response:
                # Response is in the documented format
                return {"data": response.get("data", [])}
            elif isinstance(response, list):
                # Response is a list of results
                formatted_data = []
                for item in response:
                    if isinstance(item, dict):
                        formatted_data.append(item)
                    else:
                        # Handle non-dict items (like objects)
                        formatted_data.append(
                            {
                                "url": getattr(item, "url", ""),
                                "markdown": getattr(item, "markdown", "")
                                or getattr(item, "content", ""),
                                "title": getattr(item, "title", "")
                                or getattr(item, "metadata", {}).get("title", ""),
                            }
                        )
                return {"data": formatted_data}
            else:
                print(f"Unexpected response format from Firecrawl: {type(response)}")
                return {"data": []}

        except Exception as e:
            print(f"Error searching with Firecrawl: {e}")
            print(
                f"Response type: {type(response) if 'response' in locals() else 'N/A'}"
            )
            return {"data": []}


# Initialize Firecrawl
firecrawl = Firecrawl(
    api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
    api_url=os.environ.get("FIRECRAWL_BASE_URL"),
)


class SerpQueryResponse(BaseModel):
    queries: List[SerpQuery]


async def generate_serp_queries(
    query: str,
    client: openai.OpenAI,
    model: str,
    num_queries: int = 3,
    learnings: Optional[List[str]] = None,
) -> List[SerpQuery]:
    """Generate SERP queries based on user input and previous learnings."""

    prompt = f"""Given the following prompt from the user, generate a list of SERP queries to research the topic. Return a JSON object with a 'queries' array field containing {num_queries} queries (or less if the original prompt is clear). Each query object should have 'query' and 'research_goal' fields. Notice that 'query' must be a simple question that can be answered directly through google search engine. Make sure each query is unique and not similar to each other: <prompt>{query}</prompt>"""

    if learnings:
        prompt += f"\n\nHere are some learnings from previous research, use them to generate more specific queries: {' '.join(learnings)}"

    response = await generate_completions(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": prompt},
        ],
        # format=SerpQueryResponse.model_json_schema(),
        format={"type": "json_object"},
    )

    try:
        if get_service() == "ollama":
            result = SerpQueryResponse.model_validate_json(response.message.content)
            parse_ollama_token_consume("generate_serp_queries", response)
        else:
            # json格式兜底
            json_response = response.choices[0].message.content
            try:
                json.loads(json_response) # 为正常json
            except:
                json_response = re.findall(r"```(?:json)?\s*(.*?)\s*```", json_response, re.DOTALL)[0]

            result = SerpQueryResponse.model_validate_json(
                json_response
            )
            parse_openai_token_consume("generate_serp_queries", response)

        queries = result.queries if result.queries else []
        log_event(f"Generated {len(queries)} SERP queries for research query: {query}")
        log_event(f"Got queries: {queries}")
        return queries[:num_queries]
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        log_error(
            f"Failed to parse JSON response for query: {query}, raw response: {response.choices[0].message.content}"
        )
        return []


class SerpResultResponse(BaseModel):
    learnings: List[str]
    followUpQuestions: List[str]


async def process_serp_result(
    query: str,
    search_result: SearchResponse,
    client: openai.OpenAI,
    model: str,
    num_learnings: int = 3,
    num_follow_up_questions: int = 3,
) -> Dict[str, List[str]]:
    """Process search results to extract learnings and follow-up questions."""

    contents = [
        trim_prompt(item.get("markdown", ""), 25_000)
        for item in search_result["data"]
        if item.get("markdown")
    ]

    # Create the contents string separately
    contents_str = "".join(f"<content>\n{content}\n</content>" for content in contents)

    prompt = (
        f"Given the following contents from a SERP search for the query <query>{query}</query>, "
        f"generate a list of learnings from the contents. Return a JSON object with 'learnings' "
        f"and 'followUpQuestions' keys with array of strings as values. Include up to {num_learnings} learnings and "
        f"{num_follow_up_questions} follow-up questions. Notice that 'followUpQuestions' must be a simple question that can be answered directly through google search engine. The learnings should be unique, "
        "concise, and information-dense, including entities, metrics, numbers, and dates.\n\n"
        f"<contents>{contents_str}</contents>"
    )

    response = await generate_completions(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": prompt},
        ],
        # format=SerpResultResponse.model_json_schema(),
        format={"type": "json_object"},
    )

    try:
        if get_service() == "ollama":
            result = SerpResultResponse.model_validate_json(response.message.content)
            parse_ollama_token_consume("process_serp_result", response)
        else:

            # json格式兜底
            json_response = response.choices[0].message.content
            try:
                json.loads(json_response) # 为正常json
            except:
                json_response =re.findall(r"```(?:json)?\s*(.*?)\s*```", json_response, re.DOTALL)[0]

            result = SerpResultResponse.model_validate_json(
                json_response
            )
            parse_openai_token_consume("process_serp_result", response)

        log_event(
            f"Processed SERP results for query: {query}, found {len(result.learnings)} learnings and {len(result.followUpQuestions)} follow-up questions"
        )
        log_event(
            f"Got learnings: {len(result.learnings)} and follow-up questions: {len(result.followUpQuestions)}"
        )
        return {
            "learnings": result.learnings[:num_learnings],
            "followUpQuestions": result.followUpQuestions[:num_follow_up_questions],
        }
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        log_error(
            f"Failed to parse SERP results for query: {query}, raw response: {response.choices[0].message.content}"
        )
        return {"learnings": [], "followUpQuestions": []}


class FinalReportResponse(BaseModel):
    reportMarkdown: str

import sys
sys.path.append('../deep_research_py')
from gen_outline_acticle import *
async def write_final_report(
    prompt: str,
    learnings: List[str],
    visited_urls: List[str],
    client: openai.OpenAI,
    model: str,
    writing_method="serial"
) -> str:
    """Generate final report based on all research learnings."""

    learnings_string = trim_prompt(
        "\n".join([f"<learning>\n{learning}\n</learning>" for learning in learnings]),
        150_000,
    )

    user_prompt = (
        f"Given the following prompt from the user, write a final report on the topic using "
        f"the learnings from research. Return a JSON object with a 'reportMarkdown' field "
        f"containing a detailed markdown report (aim for 3+ pages). Include ALL the learnings "
        f"from research:\n\n<prompt>{prompt}</prompt>\n\n"
        f"Here are all the learnings from research:\n\n<learnings>\n{learnings_string}\n</learnings>"
    )

    # step1: 生成outline
    draft_outlines = await write_outline(prompt, learnings_string, client, model)
    print(
        f"gen draft outlines: {draft_outlines}"
    )
    log_event(f"gen draft outlines: {draft_outlines}")

    # # step2: 润色outline
    outlines = await write_outline_polish(prompt, learnings_string, client, model, draft_outlines)
    print(
        f"gen polish outlines: {outlines}"
    )
    log_event(f"gen polish outlines: {outlines}")
    
    # # step3: 生成文章
    report =  await generate_article(prompt, learnings_string, client, model, outlines, writing_method)
    

    try:
        # if get_service() == "ollama":
        #     result = FinalReportResponse.model_validate_json(response.message.content)
        #     parse_ollama_token_consume("write_final_report", response)
        # else:
        #     result = FinalReportResponse.model_validate_json(
        #         response.choices[0].message.content
        #     )
        #     parse_openai_token_consume("write_final_report", response)

        # report = result.reportMarkdown if result.reportMarkdown else ""
        log_event(
            f"Generated final report based on {len(learnings)} learnings from {len(visited_urls)} sources"
        )
        # Append sources
        urls_section = "\n\n## Sources\n\n" + "\n".join(
            [f"- {url}" for url in visited_urls]
        )
        return report + urls_section
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}")
        # print(f"Raw response: {response.choices[0].message.content}")
        log_error(
            f"Failed to generate final report for research query, raw response:"
        )
        return "Error generating report"


async def deep_research(
    query: str,
    breadth: int,
    depth: int,
    concurrency: int,
    client: openai.OpenAI,
    model: str,
    learnings: List[str] = None,
    visited_urls: List[str] = None,
) -> ResearchResult:
    """
    Main research function that recursively explores a topic.

    Args:
        query: Research query/topic
        breadth: Number of parallel searches to perform
        depth: How many levels deep to research
        learnings: Previous learnings to build upon
        visited_urls: Previously visited URLs
    """
    learnings = learnings or []
    visited_urls = visited_urls or []

    # Generate search queries
    serp_queries = await generate_serp_queries(
        query=query,
        client=client,
        model=model,
        num_queries=breadth,
        learnings=learnings,
    )

    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(concurrency)

    async def process_query(serp_query: SerpQuery) -> ResearchResult:
        async with semaphore:
            try:
                # Search for content
                result = await firecrawl.search(
                    serp_query.query, timeout=15000, limit=5
                )

                # Collect new URLs
                new_urls = [
                    item.get("url") for item in result["data"] if item.get("url")
                ]

                # Calculate new breadth and depth for next iteration
                new_breadth = max(1, breadth // 2)
                new_depth = depth - 1

                # Process the search results
                new_learnings = await process_serp_result(
                    query=serp_query.query,
                    search_result=result,
                    num_follow_up_questions=new_breadth,
                    client=client,
                    model=model,
                )

                all_learnings = learnings + new_learnings["learnings"]
                all_urls = visited_urls + new_urls

                # If we have more depth to go, continue research
                if new_depth > 0:
                    print(
                        f"Researching deeper, breadth: {new_breadth}, depth: {new_depth}"
                    )

                    next_query = f"""
                    Previous research goal: {serp_query.research_goal}
                    Follow-up research directions: {" ".join(new_learnings["followUpQuestions"])}
                    """.strip()

                    return await deep_research(
                        query=next_query,
                        breadth=new_breadth,
                        depth=new_depth,
                        concurrency=concurrency,
                        learnings=all_learnings,
                        visited_urls=all_urls,
                        client=client,
                        model=model,
                    )

                return {"learnings": all_learnings, "visited_urls": all_urls}

            except Exception as e:
                if "Timeout" in str(e):
                    print(f"Timeout error running query: {serp_query.query}: {e}")
                else:
                    print(f"Error running query: {serp_query.query}: {e}")
                return {"learnings": [], "visited_urls": []}

    # Process all queries concurrently
    results = await asyncio.gather(*[process_query(query) for query in serp_queries])

    # Combine all results
    all_learnings = list(
        set(learning for result in results for learning in result["learnings"])
    )

    all_urls = list(set(url for result in results for url in result["visited_urls"]))

    return {"learnings": all_learnings, "visited_urls": all_urls}
