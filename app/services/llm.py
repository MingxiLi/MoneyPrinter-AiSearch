import logging
import re
import json
from typing import List
from loguru import logger
from openai import OpenAI
from openai import AzureOpenAI
from openai.types.chat import ChatCompletion

from app.config import config


def _generate_response(prompt: str) -> str:
    content = ""
    llm_provider = config.app.get("llm_provider", "openai")
    logger.info(f"llm provider: {llm_provider}")
    if llm_provider == "g4f":
        model_name = config.app.get("g4f_model_name", "")
        if not model_name:
            model_name = "gpt-3.5-turbo-16k-0613"
        import g4f
        content = g4f.ChatCompletion.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )
    else:
        api_version = ""  # for azure
        if llm_provider == "moonshot":
            api_key = config.app.get("moonshot_api_key")
            model_name = config.app.get("moonshot_model_name")
            base_url = "https://api.moonshot.cn/v1"
        elif llm_provider == "ollama":
            # api_key = config.app.get("openai_api_key")
            api_key = "ollama"  # any string works but you are required to have one
            model_name = config.app.get("ollama_model_name")
            base_url = config.app.get("ollama_base_url", "")
            if not base_url:
                base_url = "http://localhost:11434/v1"
        elif llm_provider == "openai":
            api_key = config.app.get("openai_api_key")
            model_name = config.app.get("openai_model_name")
            base_url = config.app.get("openai_base_url", "")
            if not base_url:
                base_url = "https://api.openai.com/v1"
        elif llm_provider == "oneapi":
            api_key = config.app.get("oneapi_api_key")
            model_name = config.app.get("oneapi_model_name")
            base_url = config.app.get("oneapi_base_url", "")
        elif llm_provider == "azure":
            api_key = config.app.get("azure_api_key")
            model_name = config.app.get("azure_model_name")
            base_url = config.app.get("azure_base_url", "")
            api_version = config.app.get("azure_api_version", "2024-02-15-preview")
        elif llm_provider == "gemini":
            api_key = config.app.get("gemini_api_key")
            model_name = config.app.get("gemini_model_name")
            base_url = "***"
        elif llm_provider == "qwen":
            api_key = config.app.get("qwen_api_key")
            model_name = config.app.get("qwen_model_name")
            base_url = "***"
        elif llm_provider == "cloudflare":
            api_key = config.app.get("cloudflare_api_key")
            model_name = config.app.get("cloudflare_model_name")
            account_id = config.app.get("cloudflare_account_id")
            base_url = "***"
        else:
            raise ValueError("llm_provider is not set, please set it in the config.toml file.")

        if not api_key:
            raise ValueError(f"{llm_provider}: api_key is not set, please set it in the config.toml file.")
        if not model_name:
            raise ValueError(f"{llm_provider}: model_name is not set, please set it in the config.toml file.")
        if not base_url:
            raise ValueError(f"{llm_provider}: base_url is not set, please set it in the config.toml file.")

        if llm_provider == "qwen":
            import dashscope
            from dashscope.api_entities.dashscope_response import GenerationResponse
            dashscope.api_key = api_key
            response = dashscope.Generation.call(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            if response:
                if isinstance(response, GenerationResponse):
                    status_code = response.status_code
                    if status_code != 200:
                        raise Exception(
                            f"[{llm_provider}] returned an error response: \"{response}\"")

                    content = response["output"]["text"]
                    return content.replace("\n", "")
                else:
                    raise Exception(
                        f"[{llm_provider}] returned an invalid response: \"{response}\"")
            else:
                raise Exception(
                    f"[{llm_provider}] returned an empty response")

        if llm_provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key, transport='rest')

            generation_config = {
                "temperature": 0.5,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 2048,
            }

            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
            ]

            model = genai.GenerativeModel(model_name=model_name,
                                          generation_config=generation_config,
                                          safety_settings=safety_settings)

            try:
                response = model.generate_content(prompt)
                candidates = response.candidates
                generated_text = candidates[0].content.parts[0].text
            except (AttributeError, IndexError) as e:
                print("Gemini Error:", e)

            return generated_text

        if llm_provider == "cloudflare":
            import requests
            response = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "messages": [
                        {"role": "system", "content": "You are a friendly assistant"},
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            result = response.json()
            logger.info(result)
            return result["result"]["response"]

        if llm_provider == "azure":
            client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=base_url,
            )
        else:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )

        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        if response:
            if isinstance(response, ChatCompletion):
                content = response.choices[0].message.content
            else:
                raise Exception(
                    f"[{llm_provider}] returned an invalid response: \"{response}\", please check your network "
                    f"connection and try again.")
        else:
            raise Exception(
                f"[{llm_provider}] returned an empty response, please check your network connection and try again.")

    return content.replace("\n", "")


def generate_script(video_subject: str, language: str = "", paragraph_number: int = 1) -> str:
    prompt = f"""
# Role: Video Script Generator

## Goals:
Generate a brief script for a video, depending on the subject of the video.

## Constrains:
1. the script is to be returned as a string with the specified number of paragraphs.
2. do not under any circumstance reference this prompt in your response.
3. get straight to the point, don't start with unnecessary things like, "welcome to this video".
4. you must not include any type of markdown or formatting in the script, never use a title.
5. only return the raw content of the script.
6. do not include "voiceover", "narrator" or similar indicators of what should be spoken at the beginning of each paragraph or line.
7. you must not mention the prompt, or anything about the script itself. also, never talk about the amount of paragraphs or lines. just write the script.
8. respond in the same language as the video subject.

# Initialization:
- video subject: {video_subject}
- number of paragraphs: {paragraph_number}
""".strip()
    if language:
        prompt += f"\n- language: {language}"

    final_script = ""
    logger.info(f"subject: {video_subject}")
    logger.debug(f"prompt: \n{prompt}")
    response = _generate_response(prompt=prompt)

    # Return the generated script
    if response:
        # Clean the script
        # Remove asterisks, hashes
        response = response.replace("*", "")
        response = response.replace("#", "")

        # Remove markdown syntax
        response = re.sub(r"\[.*\]", "", response)
        response = re.sub(r"\(.*\)", "", response)

        # Split the script into paragraphs
        paragraphs = response.split("\n\n")

        # Select the specified number of paragraphs
        selected_paragraphs = paragraphs[:paragraph_number]

        # Join the selected paragraphs into a single string
        final_script = "\n\n".join(selected_paragraphs)

        # Print to console the number of paragraphs used
        # logger.info(f"number of paragraphs used: {len(selected_paragraphs)}")
    else:
        logging.error("gpt returned an empty response")

    logger.success(f"completed: \n{final_script}")
    return final_script


def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> List[str]:
    prompt = f"""
# Role: Video Search Terms Generator for

## Goals:
Generate {amount} search terms for stock videos, depending on the subject of a video.

## Constrains:
1. the search terms are to be returned as a json-array of strings.
2. each search term should consist of 1-3 words
3. you must only return the json-array of strings. you must not return anything else. you must not return the script.
4. the search terms must be related to the subject of the video.
5. reply in the same language as as the video subject.

## Output Example:
["search term 1", "search term 2", "search term 3","search term 4","search term 5"]

## Context:
### Video Subject
{video_subject}

### Video Script
{video_script}

""".strip()

# Please note that you must use English for generating video search terms; Chinese is not accepted.
    logger.info(f"subject: {video_subject}")
    logger.debug(f"prompt: \n{prompt}")
    response = _generate_response(prompt)
    search_terms = []

    try:
        search_terms = json.loads(response)
        if not isinstance(search_terms, list) or not all(isinstance(term, str) for term in search_terms):
            raise ValueError("response is not a list of strings.")

    except (json.JSONDecodeError, ValueError):
        # logger.warning(f"gpt returned an unformatted response. attempting to clean...")
        # Attempt to extract list-like string and convert to list
        match = re.search(r'\["(?:[^"\\]|\\.)*"(?:,\s*"[^"\\]*")*\]', response)
        if match:
            try:
                search_terms = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error(f"could not parse response: {response}")
                return []

    logger.success(f"completed: \n{search_terms}")
    return search_terms


def generate_prompt(subject: str, script: str) -> List[str]:
    prompt = f"""
# Role: Prompt Generator for CLIP model

## Goals:
Generate prompt for CLIP model. The prompt will be used to search for images matching input script considering the input subject.

## Constrains:
1. the prompt is to be returned as a string.
2. you must only return the string. you must not return anything else. you must not return the script and must not return the word 'prompt'.
3. you must be in consideration of context of the subject
4. you must reply in the same language as the script.

## Output Example:
"prompt"

## Context:
### subject
{subject}
### script
{script}

""".strip()

    logger.info(f"prompt: {prompt}")
    response = _generate_response(prompt)
    logger.success(f"completed: \n{response}")
    return response


# def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> List[str]:
#     prompt = f"""
# # Role: summaries of storyboard of Video Shooting Script

# ## Goals:
# Generate {amount} summaries of storyboard of shooting script for stock videos.

# ## Constrains:
# 1. the summaries are to be returned as a json-array of strings.
# 2. each summary should consist of 1-3 words
# 3. you must only return the json-array of strings. you must not return anything else. you must not return the script.
# 4. the summaries must be related to the subject of the video.
# 5. reply in Chinese.

# ## Output Example:
# ["summary 1", "summary 2", "summary 3","summary 4","summary 5"]

# ## Context:
# ### Video Subject
# {video_subject}

# ### Video Script
# {video_script}

# """.strip()

# # Please note that you must use English for generating video search terms; Chinese is not accepted.
#     logger.info(f"subject: {video_subject}")
#     logger.debug(f"prompt: \n{prompt}")
#     response = _generate_response(prompt)
#     search_terms = []

#     try:
#         search_terms = json.loads(response)
#         if not isinstance(search_terms, list) or not all(isinstance(term, str) for term in search_terms):
#             raise ValueError("response is not a list of strings.")

#     except (json.JSONDecodeError, ValueError):
#         # logger.warning(f"gpt returned an unformatted response. attempting to clean...")
#         # Attempt to extract list-like string and convert to list
#         match = re.search(r'\["(?:[^"\\]|\\.)*"(?:,\s*"[^"\\]*")*\]', response)
#         if match:
#             try:
#                 search_terms = json.loads(match.group())
#             except json.JSONDecodeError:
#                 logger.error(f"could not parse response: {response}")
#                 return []

#     logger.success(f"completed: \n{search_terms}")
#     return search_terms


if __name__ == "__main__":
    video_subject = "生命的意义是什么"
    script = generate_script(video_subject=video_subject, language="zh-CN", paragraph_number=1)
    # print("######################")
    # print(script)
    # search_terms = generate_terms(video_subject=video_subject, video_script=script, amount=5)
    # print("######################")
    # print(search_terms)
