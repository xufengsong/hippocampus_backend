import asyncio
import cognee
from cognee.infrastructure.engine.models.Edge import Edge
from cognee.api.v1.visualize.visualize import visualize_graph
from cognee.infrastructure.databases.graph import graph_engin
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    await cognee.add("./the-illusion-of-thinking.pdf", node_set="user_1-ai-hallucination-4MBE")
    await cognee.cognify()

    # await visualize_graph("./graph_after_cognify.html")

asyncio.run(main())