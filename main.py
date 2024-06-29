import logging
import re
import os
import json
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from flask import Flask, request
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Define states for conversation flow
SELECTING_CHAIN, TYPING_TOKEN, TYPING_PORTAL, SELECTING_SLOT, SELECTING_PERIOD, CONFIRMING_ORDER = range(6)

# Prices dictionary
PRICES = {
    'Top 3 Guarantee': {
        '3 hours': '5.6',
        '6 hours': '9.92',
        '12 hours': '17.92',
        '24 hours': '29.92'
    },
    'Top 8 Guarantee': {
        '3 hours': '4.65',
        '6 hours': '8.37',
        '12 hours': '14.48',
        '24 hours': '25.92'
    },
    'Any position': {
        '3 hours': '3.85',
        '6 hours': '6.93',
        '12 hours': '12.32',
        '24 hours': '21.56'
    }
}

# Define a few command handlers. These usually take the two arguments update and context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a message when the command /start is issued."""
    logger.info("Received /start command")
    keyboard = [
        [InlineKeyboardButton("ETH", callback_data='ETH')],
        [InlineKeyboardButton("BNB", callback_data='BNB')],
        [InlineKeyboardButton("SOL", callback_data='SOL')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text('Select chain:', reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text('Select chain:', reply_markup=reply_markup)
    
    return SELECTING_CHAIN

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=" Send me token address.")
    
    # Store the chain selection in the context for future use
    context.user_data['chain'] = query.data
    logger.info(f"Chain selected: {query.data}")
    return TYPING_TOKEN

async def token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle token address input."""
    user_address = update.message.text
    context.user_data['token_address'] = user_address
    logger.info(f"Token address received: {user_address}")

    # Ask the user what they want to order
    order_keyboard = [
        [InlineKeyboardButton("Trending Fast-Track", callback_data='Fast-Track')]
    ]
    order_reply_markup = InlineKeyboardMarkup(order_keyboard)
    await update.message.reply_text('What do you want to order?', reply_markup=order_reply_markup)
    return SELECTING_SLOT

async def order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle order selection."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="❔ Send me portal/group link.")
    logger.info(f"Order selected: {query.data}")
    return TYPING_PORTAL

async def portal_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle portal/group link input."""
    portal_link = update.message.text
    # Regex pattern to validate a Telegram link
    telegram_link_pattern = re.compile(r'(https?://)?(www\.)?(t\.me|telegram\.me)/[a-zA-Z0-9_]+')
    
    if telegram_link_pattern.match(portal_link):
        context.user_data['portal_link'] = portal_link
        logger.info(f"Portal link received: {portal_link}")
        # Ask the user to select an open slot
        slot_keyboard = [
            [
                InlineKeyboardButton("🟢 Top 3 Guarantee", callback_data='Top 3 Guarantee'),
                InlineKeyboardButton("🔴 Top 8 Guarantee", callback_data='Top 8 Guarantee')
            ],
            [InlineKeyboardButton("🟢 Any position", callback_data='Any position')]
        ]
        slot_reply_markup = InlineKeyboardMarkup(slot_keyboard)
        await update.message.reply_text(
            'ℹ Select open slot or click to see the nearest potential availability time:',
            reply_markup=slot_reply_markup
        )
        return SELECTING_SLOT
    else:
        await update.message.reply_text("❗️ Incorrect portal or group link.")
        logger.warning("Incorrect portal or group link received")
        return TYPING_PORTAL

async def slot_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle slot selection."""
    query = update.callback_query
    await query.answer()
    context.user_data['slot'] = query.data
    logger.info(f"Slot selected: {query.data}")
    
    # Present period options
    period_keyboard = [
        [
            InlineKeyboardButton("3 hours", callback_data='3 hours'),
            InlineKeyboardButton("6 hours | -10%", callback_data='6 hours')
        ],
        [
            InlineKeyboardButton("12 hours | -20%", callback_data='12 hours'),
            InlineKeyboardButton("24 hours | -30%", callback_data='24 hours')
        ]
    ]
    period_reply_markup = InlineKeyboardMarkup(period_keyboard)
    await query.message.reply_text('❔ Select period:', reply_markup=period_reply_markup)
    return SELECTING_PERIOD

async def period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle period selection."""
    query = update.callback_query
    await query.answer()
    context.user_data['period'] = query.data
    logger.info(f"Period selected: {query.data}")
    
    # Gather all the details for confirmation
    token_address = context.user_data.get('token_address')
    chain = context.user_data.get('chain')
    portal_link = context.user_data.get('portal_link')
    slot = context.user_data.get('slot')
    period = query.data
    price = PRICES[slot][period]  # Retrieve the price from the dictionary

    # Send confirmation message
    confirmation_message = (
       f"<b>Confirm your order:</b>\n\n" 
f"<b>Token Address:</b> <b>{token_address}</b>\n" 
f"<b>Chain:</b> <b>{chain}</b>\n"
f"<b>Portal:</b> <b>{portal_link}</b>\n" 
f"<b>Time:</b> <b>{period}</b>\n" 
f"<b>Top:</b> <b>{slot}</b>\n" 
f"<b>Price:</b> <b>{price} SOL</b>\n\n"
        'Be sure to read full message before you continue, by clicking "✅ Confirm" button below you also confirm that you understand and accept rules:\n'
        '1. Deluge.Cash team can remove your token from the trending list with no chance of a refund if they suspect a scam in your token (ex.: sell tax 99%, developer mints a lot of tokens, liquidity removal and etc.) or abandoned project or lack of telegram group moderation or false information or deception or NSFW content in group or any place where links in channel/group leads to including "portals" to group.\n' 
        "2. You must ensure that your advertisement, links to channels or groups you provide and any related materials posted, distributed or linked to in a group or channel you provide do not provide false information, deception, sexual or any NSFW (Not Safe For Work) content. This includes, but is not limited to, any material that is pornographic, sexually explicit, or otherwise inappropriate for a general audience.\n"
        "3. You are forbidden from including or linking to pornography, sexually explicit images, videos, or other materials, whether real or simulated, in your advertisement.\n"
        "4. You must avoid including sexually suggestive content in your advertisement, including images, videos, text, and any other forms of media intended to arouse.\n"
        "5. You must ensure that your advertisement do not involve scams or fraudulent schemes intended to deceive others for financial gain or other benefits.\n"
        '6. If suspicious activity in the form of "farming" (developers keeping more than 14%, splitting wallets) is noticed and according to the Deluge.Cash team it may be a threat, your token will be removed from trending list, refund is not available.\n'
        "7. You should also realize that the position in the trending list has NO IMPACT on the chances of sending a buy in the trending channel, chances of sending buy to channel: ~25% for buys >10$ if @buybot setted up in group.\n"
        "8. For violation of any of the above rules your token will be removed from trending list, refund is not available.\n"
        "9. Refund can be made only in case of full service disruption (stop updating trending list and your token not in the list and full stop displaying buys in the channel) more than 20 minutes straight and to the address of the wallet from which the payment was made to the address for payment, do NOT send payment from exchanges or wallets to which you do not have access because you will not be refunded, use only your personal wallet to which you will always have access."
    )
    confirm_keyboard = [
        [InlineKeyboardButton("✅ Confirm", callback_data='confirm_order')],
        [InlineKeyboardButton("🔄 Cancel and start over", callback_data='cancel_and_start_over')]
    ]
    confirm_reply_markup = InlineKeyboardMarkup(confirm_keyboard)

    await query.edit_message_text(confirmation_message, reply_markup=confirm_reply_markup, parse_mode=ParseMode.HTML)
    
    return CONFIRMING_ORDER

async def cancel_and_start_over(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle cancel and start over."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Order cancelled. Starting over.")
    return await start(query, context)

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delete command."""
    delete_keyboard = [
        [InlineKeyboardButton("✅ Yes, I'm sure", callback_data='confirm_delete')],
        [InlineKeyboardButton("❗️ No", callback_data='cancel_delete')]
    ]
    delete_reply_markup = InlineKeyboardMarkup(delete_keyboard)
    await update.message.reply_text(
        'Are you sure to delete all configuration data?\n'
        'Do not do this if you have paid or are about to pay for this configuration, '
        'as a new payment wallet will be generated next time!',
        reply_markup=delete_reply_markup
    )

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation of delete."""
    query = update.callback_query
    await query.answer()
    
    # Clear user data
    context.user_data.clear()
    logger.info("All configuration data has been deleted.")
    
    return await start(query, context)

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle cancellation of delete."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Deletion cancelled.")
    logger.info("Deletion cancelled.")
    # End the conversation
    return ConversationHandler.END

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle order confirmation."""
    query = update.callback_query
    await query.answer()
    
    # Retrieve user-entered data
    token_address = context.user_data.get('token_address')
    chain = context.user_data.get('chain')
    portal_link = context.user_data.get('portal_link')
    slot = context.user_data.get('slot')
    period = context.user_data.get('period')
    price = PRICES[slot][period]  # Retrieve the price from the dictionary
    
    logger.info(f"Order confirmed: Token Address: {token_address}, Chain: {chain}, Portal: {portal_link}, Slot: {slot}, Period: {period}, Price: {price}")

    payment_information = (
        "❔ <b>Payment Information:</b>\n\n"
        "⤵️<b> Always double-check that you have entered the correct address before sending.</b>\n"
        f"<b>Address:</b> <code>G2XNkLGnHeFTCj5Eb328t49aV2xL3rYmrwugg4n3BPHm</code>\n"
        f"<b>Amount:</b> <code>{price}</code><b> SOL</b>\n\n"
        "<b>After the transfer, click the button below. You can transfer the rest if you haven't transferred enough.</b>\n\n"
        "<b>To cancel the payment and start over, use /delete.</b>"
    )
    
    check_payment_keyboard = [
        [InlineKeyboardButton("Check payment", callback_data='check_payment')]
    ]
    check_payment_reply_markup = InlineKeyboardMarkup(check_payment_keyboard)
    
    await query.edit_message_text(payment_information, reply_markup=check_payment_reply_markup, parse_mode=ParseMode.HTML)

    return ConversationHandler.END


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle check payment."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(text="❗️ Payment Not Received.")
    logger.info("Payment check executed: Payment Not Received.")

    return ConversationHandler.END

async def process_update(application, update):
    await application.process_update(update)

def main() -> None:
    """Start the bot."""
    # Use the provided token directly
    token = '7288330417:AAFcIwdAAPe90LGQ918Ao5NIPEmA8LLF9kE'
    logger.info("Starting the bot with provided token.")
    
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(token).build()

    # Define conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_CHAIN: [CallbackQueryHandler(button, pattern='^(ETH|BNB|SOL)$')],
            TYPING_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, token_address)],
            TYPING_PORTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, portal_group_link)],
            SELECTING_SLOT: [
                CallbackQueryHandler(order, pattern='^(Fast-Track)$'),
                CallbackQueryHandler(slot_selection, pattern='^(Top 3 Guarantee|Top 8 Guarantee|Any position)$')
            ],
            SELECTING_PERIOD: [
                CallbackQueryHandler(period_selection, pattern='^(3 hours|6 hours|12 hours|24 hours)$')
            ],
            CONFIRMING_ORDER: [
                CallbackQueryHandler(confirm_order, pattern='^confirm_order$'),
                CallbackQueryHandler(cancel_and_start_over, pattern='^cancel_and_start_over$'),
                CallbackQueryHandler(confirm_delete, pattern='^confirm_delete$'),
                CallbackQueryHandler(cancel_delete, pattern='^cancel_delete$')
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    # Add conversation handler to application
    application.add_handler(conv_handler)

    # Add delete command handler
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CallbackQueryHandler(confirm_delete, pattern='^confirm_delete$'))
    application.add_handler(CallbackQueryHandler(cancel_delete, pattern='^cancel_delete$'))
    
    # Add check payment handler
    application.add_handler(CallbackQueryHandler(check_payment, pattern='^check_payment$'))

    # Create a Flask app
    app = Flask(__name__)

    @app.route('/', methods=['GET'])
    def index():
        return 'Hello World!'

    @app.route('/webhook', methods=['POST'])
    def webhook():
        json_str = request.get_data(as_text=True)
        data = json.loads(json_str)  # Parse the JSON data
        logger.info(f"Webhook received data: {data}")
        update = Update.de_json(data, application.bot)
        asyncio.run(process_update(application, update))
        return 'ok'

    # Function to set webhook
    async def set_webhook():
        webhook_url = 'https://tsouria.onrender.com/webhook'  # Replace with your actual domain
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")

    # Set webhook after the app is running
    async def on_startup():
        await set_webhook()

    # Run the webhook listener in a separate task
    asyncio.run(on_startup())

    # Start the Flask app
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask app on port: {port}")
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()
