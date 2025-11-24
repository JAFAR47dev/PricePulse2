# handlers/funfact.py
import random
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

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
    "Bitcoin halvings occur every 210,000 blocks, roughly every 4 years.",
    "The Ethereum Merge in 2022 reduced its energy usage by over 99%.",
    "The term 'whale' refers to someone who holds large amounts of crypto.",
    "Chainlink provides real-world data to smart contracts through 'oracles'.",
    "Shiba Inu once surpassed Dogecoin in market cap temporarily.",
    "Cardano is named after Gerolamo Cardano, a 16th-century mathematician.",
    "The creator of Litecoin, Charlie Lee, sold all his LTC at its peak in 2017.",
    "Polygon (MATIC) helps scale Ethereum using sidechains and rollups.",
    "The most expensive NFT ever sold is Beeple's artwork for $69 million.",
    "Crypto wallets can be hot (online) or cold (offline).",
    "Smart contracts are self-executing agreements written in code.",
    "Bitcoin was created in response to the 2008 financial crisis.",
    "Solana can process up to 65,000 transactions per second.",
    "Ripple (XRP) aims to be the bridge between traditional banking and crypto.",
    "NFTs stand for Non-Fungible Tokens — unique digital assets.",
    "The first ICO ever was Mastercoin in 2013.",
    "Tether (USDT) was the first widely-used stablecoin.",
    "Proof of Work (PoW) and Proof of Stake (PoS) are consensus mechanisms.",
    "Countries like China have banned crypto trading multiple times.",
    "You don’t need to buy a full Bitcoin — it's divisible into 100 million satoshis.",
    "Satoshi Nakamoto is estimated to be worth over $40 billion.",
    "Ethereum's founder once wrote for Bitcoin Magazine.",
    "The NFT boom started with collectibles like CryptoPunks and CryptoKitties.",
    "Axie Infinity players in the Philippines earned real income during COVID.",
    "The Lightning Network enables fast, low-fee Bitcoin payments.",
    "DAOs (Decentralized Autonomous Organizations) are communities governed by code.",
    "Some governments use blockchain for voting and land records.",
    "The phrase ‘Not your keys, not your coins’ means control lies in private keys.",
    "Crypto is banned or restricted in over 40 countries.",
    "Hardware wallets like Ledger and Trezor store crypto offline securely.",
    "Web3 refers to the next generation of the internet powered by blockchain.",
    "Ethereum plans to introduce sharding for better scalability.",
    "NFTs can represent anything — from digital art to real estate deeds.",
    "Bitcoin mining consumes more electricity than some countries."
]

async def funfact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/funfact")
    await handle_streak(update, context)

    fact = random.choice(FUN_FACTS)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Random", callback_data="funfact_random")]]
    )

    await update.message.reply_text(
        f"🤓 *Crypto Fun Fact*\n\n{fact}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    
async def funfact_random_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    fact = random.choice(FUN_FACTS)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Random", callback_data="funfact_random")]]
    )

    # Edit the same message
    await query.message.edit_text(
        f"🤓 *Crypto Fun Fact*\n\n{fact}",
        parse_mode="Markdown",
        reply_markup=keyboard
    )