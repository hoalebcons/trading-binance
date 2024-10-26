from binance.client import Client
import pandas as pd
import talib
from datetime import datetime, timedelta
import time

# Thay thế bằng API Key và Secret của bạn
api_key = ''
api_secret = ''

# Khởi tạo Client
client = Client(api_key, api_secret)

# Các tham số có thể tùy chỉnh
symbol = 'STRKUSDT'  # Cặp giao dịch
volume = 20        # Khối lượng mỗi giao dịch
upper = 66          # RSI upper để mở Short
lower = 40          # RSI lower để mở Long
leverage = 2        # Đòn bẩy X2 cho giao dịch Futures

# 1. Thiết lập đòn bẩy và chế độ ký quỹ Isolated cho Binance Futures
def set_leverage(symbol, leverage):
    try:
        response = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Đòn bẩy đã được thiết lập: {response['leverage']}x cho {symbol}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi thiết lập đòn bẩy cho {symbol}: {e}")

def set_margin_mode_isolated(symbol):
    try:
        response = client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
        print(f"Chế độ ký quỹ được đặt thành Isolated cho {symbol}")
    except Exception as e:
        if "No need to change margin type." in str(e):
            print(f"{symbol} đã được đặt chế độ Isolated.")
        else:
            print(f"Đã xảy ra lỗi khi đặt chế độ ký quỹ Isolated cho {symbol}: {e}")

# 2. Lấy thời gian hiện tại và làm tròn xuống giờ gần nhất
def get_current_rounded_time():
    # Lấy thời gian hiện tại và trừ đi 7 giờ để chuyển từ UTC sang giờ UTC+7 (Asia/Ho_Chi_Minh)
    now = datetime.utcnow() + timedelta(hours=7)
    now = now.replace(second=0, microsecond=0)
    
    # Làm tròn giờ nếu không phải đúng giờ chẵn (nếu cần)
    if now.minute != 0:
        now = now - timedelta(minutes=now.minute)
    return now

# 3. Lấy dữ liệu lịch sử từ Binance
def get_historical_data(symbol, interval, lookback_hours=140):
    end_time = get_current_rounded_time()
    start_time = end_time - timedelta(hours=lookback_hours)
    
    # Định dạng thời gian cho API
    adjusted_start = start_time.strftime("%Y-%m-%d %H:%M:%S")
    adjusted_end = end_time.strftime("%Y-%m-%d %H:%M:%S")

    # Lấy dữ liệu từ Binance
    klines = client.futures_historical_klines(symbol, interval, adjusted_start, adjusted_end)

    # Tạo DataFrame từ dữ liệu lấy được
    df = pd.DataFrame(klines, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time',
                                       'Quote_asset_volume', 'Number_of_trades', 'Taker_buy_base_asset_volume',
                                       'Taker_buy_quote_asset_volume', 'Ignore'])
    
    # Chỉ giữ lại các cột cần thiết: Time, Close (Price) và Volume
    df = df[['Time', 'Open', 'High', 'Low', 'Close', 'Volume']]
    
    # Chuyển đổi Time thành định dạng dễ đọc và giữ ở UTC
    df['Time'] = pd.to_datetime(df['Time'], unit='ms', utc=True)
    
    # Chuyển Time sang múi giờ 'Asia/Ho_Chi_Minh' nếu cần
    df['Time'] = df['Time'].dt.tz_convert('Asia/Ho_Chi_Minh')

    df['Open'] = pd.to_numeric(df['Open'])
    df['High'] = pd.to_numeric(df['High'])
    df['Low'] = pd.to_numeric(df['Low'])
    df['Close'] = pd.to_numeric(df['Close'])
    df['Volume'] = pd.to_numeric(df['Volume'])
    df.rename(columns={'Close': 'Price'}, inplace=True)
    
    return df

# 4. Tính toán các chỉ báo kỹ thuật
def calculate_indicators(df):
    df['RSI'] = talib.RSI(df['Price'], timeperiod=14)
    df['ATR'] = talib.ATR(df['High'], df['Low'], df['Price'], timeperiod=14)
    return df.dropna()

# 5. Đặt lệnh LONG
def place_futures_long(quantity):
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='MARKET',
            quantity=quantity
        )
        print(f"Lệnh LONG thành công: {order}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đặt lệnh LONG: {e}")

# 6. Đặt lệnh SHORT
def place_futures_short(quantity):
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='MARKET',
            quantity=quantity
        )
        print(f"Lệnh SHORT thành công: {order}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đặt lệnh SHORT: {e}")

# 7. Đặt Stop Loss
def place_stop_loss(stop_loss_price, position):
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side='SELL' if position == 'long' else 'BUY',
            type='STOP_MARKET',
            stopPrice=stop_loss_price,
            closePosition=True
        )
        print(f"Đặt Stop Loss thành công: {order}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đặt lệnh Stop Loss: {e}")

# 8. Đặt Take Profit
def place_take_profit(take_profit_price, position):
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side='SELL' if position == 'long' else 'BUY',
            type='TAKE_PROFIT_MARKET',
            stopPrice=take_profit_price,
            closePosition=True
        )
        print(f"Đặt Take Profit thành công: {order}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đặt lệnh Take Profit: {e}")

# 9. Hủy lệnh Stop Loss và Take Profit
def cancel_stop_loss():
    try:
        orders = client.futures_get_open_orders(symbol=symbol)
        for order in orders:
            if order['type'] == 'STOP_MARKET':  # Tìm lệnh Stop Loss
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                print(f"Hủy lệnh Stop Loss hiện tại: {order['orderId']}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi hủy lệnh Stop Loss: {e}")

def cancel_take_profit():
    try:
        orders = client.futures_get_open_orders(symbol=symbol)
        for order in orders:
            if order['type'] == 'TAKE_PROFIT_MARKET':  # Tìm lệnh Take Profit
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                print(f"Hủy lệnh Take Profit hiện tại: {order['orderId']}")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi hủy lệnh Take Profit: {e}")

# 10. Kiểm tra trạng thái của vị thế
def check_order_status():
    try:
        
        # Kiểm tra thông tin vị thế
        positions = client.futures_position_information(symbol=symbol)

        # Kiểm tra xem có vị thế nào đang mở không
        position_amount = float(positions[0]['positionAmt'])  # Chỉ số 0 cho cặp giao dịch STRKUSDT

        if position_amount == 0:
            cancel_stop_loss()  # Hủy Stop Loss nếu không còn lệnh MARKET nào
            cancel_take_profit()  # Hủy Take Profit nếu không còn lệnh MARKET nào
            return 'empty'  # Không còn vị thế hoặc lệnh MARKET nào đang mở
        return 'open'
    except Exception as e:
        print(f"Lỗi khi kiểm tra trạng thái lệnh: {e}")
        return 'error'

# 11. Chờ đến giờ chẵn và thực hiện các hành động giao dịch
def wait_until_next_hour():
    now = datetime.utcnow()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    time_diff = (next_hour - now).total_seconds()
    print("Đang chờ đến khung giờ thích hợp")
    time.sleep(time_diff)

# 12. Chạy bot giao dịch theo chiến thuật Futures
def run_bot():
    set_leverage(symbol, leverage)
    set_margin_mode_isolated(symbol)

    position = None
    entry_price = None
    stop_loss_price = None
    take_profit_price = None

    while True:
        wait_until_next_hour()

        current_price = None
        current_rsi = None
        atr = None
        current_time = None

        while True:
            try:
                df = get_historical_data(symbol, Client.KLINE_INTERVAL_1HOUR, 200)
                df = calculate_indicators(df)

                current_time = df['Time'].iloc[-1]
                now = datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=7)
                now = pd.Timestamp(now, tz='Asia/Ho_Chi_Minh')

                if current_time >= now:
                    current_price = df['Price'].iloc[-1]
                    current_rsi = df['RSI'].iloc[-1]
                    previous_rsi = df['RSI'].iloc[-2]
                    atr = df['ATR'].iloc[-1]
                    break
                else:
                    print("Dữ liệu chưa cập nhật, chờ thêm 1 phút...")
                    time.sleep(60)

            except Exception as e:
                print(f"Lỗi xảy ra khi lấy dữ liệu: {e}")
                time.sleep(60)

        print(f"Tại thời điểm {current_time} mã {symbol} có giá {current_price} với RSI trước là {previous_rsi}")

        # Kiểm tra trạng thái lệnh và đặt lại trạng thái nếu lệnh TP/SL được kích hoạt
        if check_order_status() == 'empty':
            position = None

        if position is None:
            if current_rsi < lower:
                position = 'long'
                entry_price = current_price
                stop_loss_price = round(entry_price - (1.5 * atr), 4)
                take_profit_price = round(entry_price + (3 * atr), 4)

                place_futures_long(volume)
                place_stop_loss(stop_loss_price, position)
                place_take_profit(take_profit_price, position)
                print(f"Mở vị thế BUY tại giá {entry_price} với SL {stop_loss_price} và TP {take_profit_price}")

            elif current_rsi > upper:
                position = 'short'
                entry_price = current_price
                stop_loss_price = round(entry_price + (1.5 * atr), 4)
                take_profit_price = round(entry_price - (3 * atr), 4)

                place_futures_short(volume)
                place_stop_loss(stop_loss_price, position)
                place_take_profit(take_profit_price, position)
                print(f"Mở vị thế SELL tại giá {entry_price} với SL {stop_loss_price} và TP {take_profit_price}")

        # Cập nhật Stop Loss động nếu cần
        if position == 'long':
            if current_price > entry_price:
                new_stop_loss = round(current_price - (1.5 * atr),4)
                if new_stop_loss > stop_loss_price:
                    print(f"Cập nhật Stop Loss mới từ {stop_loss_price} lên {new_stop_loss}")
                    cancel_stop_loss()  # Hủy lệnh SL cũ
                    place_stop_loss(new_stop_loss, position)
                    stop_loss_price = new_stop_loss

        elif position == 'short':
            if current_price < entry_price:
                new_stop_loss = round(current_price + (1.5 * atr),4)
                if new_stop_loss < stop_loss_price:
                    print(f"Cập nhật Stop Loss mới từ {stop_loss_price} xuống {new_stop_loss}")
                    cancel_stop_loss()  # Hủy lệnh SL cũ
                    place_stop_loss(new_stop_loss, position)
                    stop_loss_price = new_stop_loss

# Gọi hàm chính để chạy bot
run_bot()