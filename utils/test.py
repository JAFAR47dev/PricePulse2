import asyncio
from indicators import get_crypto_indicators

async def test():
    data = await get_crypto_indicators("BTC", "1h")
    print(json.dumps(data, indent=2))

asyncio.run(test())