import asyncio
from utils.indicators import get_crypto_indicators  # replace with your actual filename


# 🧪 Example Test
async def test():
    data = await get_crypto_indicators("BTC/USD", "1h")
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    asyncio.run(test())
    