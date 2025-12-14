import asyncio
import cognee
from cognee.infrastructure.engine.models.Edge import Edge
from cognee.api.v1.visualize.visualize import visualize_graph
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    print(os.getenv("LLM_MODEL"))
    await cognee.add(["Alice knows Bob.", "NLP is a subfield of CS."])
    await cognee.cognify()

    await visualize_graph("./graph_after_cognify.html")

asyncio.run(main())

# async def main():

#     # Create a clean slate for cognee -- reset data and system state
#     await cognee.prune.prune_data()
#     await cognee.prune.prune_system(metadata=True)
    
#     # Add sample content
#     text = "Cognee turns documents into AI memory."
#     await cognee.add(text)
    
#     # Process with LLMs to build the knowledge graph
#     await cognee.cognify()
    
#     # Search the knowledge graph
#     results = await cognee.search(
#         query_text="What does Cognee do?"
#     )
    
#     # Print
#     for result in results:
#         print(result)

# if __name__ == '__main__':
#     asyncio.run(main())