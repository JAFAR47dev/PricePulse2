# handlers/funfact.py
import random
from telegram import Update
from telegram.ext import ContextTypes

FUN_FACTS = [
    "The first real-world Bitcoin transaction was for two pizzas worth 10,000 BTC in 2010.",
    "Ethereum was crowdfunded in 2014, raising $18 million — one of the earliest ICOs.",
    "Satoshi Nakamoto owns over 1 million BTC, but has never moved them.",
    "Vitalik Buterin was just 19 years old when he created Ethereum.",
    "The term 'HODL' originated from a typo in a 2013 Bitcoin forum post.",
    "There are over 24,000 cryptocurrencies — but most have no real utility.",
    "The Bitcoin network's computing power exceeds the top 500 supercomputers combined.",
    "Dogecoin started as a joke, but reached a $90B market cap in 2021.",
    "El Salvador became the first country to make Bitcoin legal tender in 2021.",
    "Lost crypto wallets with forgotten keys account for billions in unclaimed value.",
    "The total supply of Bitcoin will never exceed 21 million.",
    "Binance is the largest crypto exchange by daily trading volume.",
    "In 2011, Bitcoin reached $1 for the first time.",
    "A man once accidentally threw away a hard drive with 8,000+ BTC on it.",
    "CryptoKitties once clogged the Ethereum network in 2017.",
    "The average block time for Ethereum is ~12 seconds.",
    "Ethereum gas fees reached over $300 per transaction during peak congestion.",
    "Most NFTs are built on Ethereum’s ERC-721 standard.",
    "Blockchain cannot be hacked unless 51% of the network colludes.",
    "Bitcoin halvings occur every 210,000 blocks, roughly every 4 years."
]

async def funfact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fact = random.choice(FUN_FACTS)
    await update.message.reply_text(f"🤓 *Crypto Fun Fact*\n\n{fact}", parse_mode="Markdown")