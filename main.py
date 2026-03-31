import os
import asyncio
from dotenv import load_dotenv

from agentscope.agent import ReActAgent, UserAgent
from agentscope.memory import InMemoryMemory
from agentscope.tool import Toolkit, execute_python_code, execute_shell_command

# Gemini
from agentscope.model import GeminiChatModel
from agentscope.formatter import GeminiChatFormatter

# Qwen (décommente si tu veux utiliser Qwen à la place)
# from agentscope.model import DashScopeChatModel
# from agentscope.formatter import DashScopeChatFormatter

load_dotenv()


async def main():
    toolkit = Toolkit()
    toolkit.register_tool_function(execute_python_code)
    toolkit.register_tool_function(execute_shell_command)

    # --- Gemini ---
    model = GeminiChatModel(
        model_name="gemini-2.5-flash",
        api_key=os.environ["GEMINI_API_KEY"],
        stream=True,
    )
    formatter = GeminiChatFormatter()

    # --- Qwen (décommente ce bloc et commente Gemini au-dessus) ---
    # model = DashScopeChatModel(
    #     model_name="qwen-max",
    #     api_key=os.environ["DASHSCOPE_API_KEY"],
    #     stream=True,
    # )
    # formatter = DashScopeChatFormatter()

    agent = ReActAgent(
        name="Friday",
        sys_prompt="Tu es un assistant utile nommé Friday.",
        model=model,
        formatter=formatter,
        memory=InMemoryMemory(),
        toolkit=toolkit,
    )

    user = UserAgent(name="user")
    msg = None
    while True:
        msg = await agent(msg)
        msg = await user(msg)
        if msg.get_text_content() == "exit":
            break


asyncio.run(main())
