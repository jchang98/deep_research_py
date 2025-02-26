from openai import OpenAI
import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class OpenAIClient:
    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
        self.model = "gpt-4o-mini"  # 或者使用 "gpt-4" 等其他模型
        
    async def generate_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_completion_tokens: int = 1000,
        format: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate completion using OpenAI API.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Controls randomness (0.0-1.0)
            max_tokens: Maximum number of tokens to generate
            format: Optional JSON schema for response format
        
        Returns:
            Generated text response
        """
        try:
            if format:
                messages.append({
                    "role": "system",
                    "content": f"You must respond in the following JSON format: {format}"
                })
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating completion: {str(e)}")
            raise

# 使用示例
async def main():
    client = OpenAIClient()
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"}
    ]
    
    response = await client.generate_completion(messages)
    print(response)

    # 使用JSON格式
    format = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"}
        }
    }
    
    response = await client.generate_completion(
        messages,
        format=format,
        temperature=0.3
    )
    print(response)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())