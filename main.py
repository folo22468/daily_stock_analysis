# -*- coding: utf-8 -*-
import os
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import logging
from datetime import datetime, timedelta
from analyzer import GeminiAnalyzer
from notification import NotificationService

# 基礎日誌設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaiwanStockScanner:
    def __init__(self):
        # 這裡可以自訂你感興趣的熱門台股池，若 STOCK_LIST 為空則掃描這些
        self.default_pool = ["2330.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW", "3231.TW", "2881.TW", "2882.TW", "0050.TW", "0056.TW"]

    def get_stock_list(self):
        env_list = os.getenv('STOCK_LIST', '')
        if env_list:
            return [s.strip() if '.TW' in s.upper() else f"{s.strip()}.TW" for s in env_list.split(',')]
        return self.default_pool

    def scan_strong_stocks(self):
        stocks = self.get_stock_list()
        strong_candidates = []
        
        logger.info(f"開始掃描技術面強勢股，目標數量：{len(stocks)}")
        
        for symbol in stocks:
            try:
                # 抓取半年數據以計算周K與均線
                df = yf.download(symbol, period="1y", interval="1d", progress=False)
                if df.empty or len(df) < 60: continue

                # 1. 計算均線 (MA5, MA10, MA20)
                df['MA5'] = ta.sma(df['Close'], length=5)
                df['MA10'] = ta.sma(df['Close'], length=10)
                df['MA20'] = ta.sma(df['Close'], length=20)

                # 2. 計算 MACD (DIF, DEA)
                macd = ta.macd(df['Close'])
                df = pd.concat([df, macd], axis=1)

                # 3. 計算 KDJ
                kdj = ta.kdj(df['High'], df['Low'], df['Close'])
                df = pd.concat([df, kdj], axis=1)

                # 取最新一筆數據
                last = df.iloc[-1]
                prev = df.iloc[-2]

                # --- 強勢篩選條件 ---
                # A. 均線多頭排列
                is_ma_aligned = last['MA5'] > last['MA10'] > last['MA20']
                
                # B. MACD 金叉 (DIF > DEA 且前一日 DIF <= DEA)
                dif_col = 'MACD_12_26_9'
                dea_col = 'MACDs_12_26_9'
                is_macd_golden = last[dif_col] > last[dea_col]
                
                # C. KDJ 向上 (K > D)
                is_kdj_up = last['K_9_3'] > last['D_9_3']
                
                # D. 乖離率控制 (避免追高，收盤價距離MA20不超過5%)
                bias_20 = (last['Close'] - last['MA20']) / last['MA20']
                is_not_overheated = bias_20 < 0.05

                # 只要符合多頭且沒過熱就納入 AI 分析
                if is_ma_aligned and is_macd_golden and is_kdj_up and is_not_overheated:
                    logger.info(f"🟢 發現強勢股: {symbol}")
                    strong_candidates.append({'symbol': symbol, 'data': df.tail(10)}) # 傳送最近10日數據給AI
            except Exception as e:
                logger.error(f"掃描 {symbol} 出錯: {e}")
        
        return strong_candidates

def main():
    logger.info("台股智能分析系統啟動...")
    scanner = TaiwanStockScanner()
    strong_stocks = scanner.scan_strong_stocks()
    
    if not strong_stocks:
        logger.info("今日無符合技術面強勢條件之個股。")
        return

    # 初始化 AI 與 通知服務
    analyzer = GeminiAnalyzer()
    notifier = NotificationService()
    
    final_reports = []
    
    # 針對篩選出的強勢股進行 AI 深度分析
    for item in strong_stocks[:30]: # 最多分析前30檔
        symbol = item['symbol']
        # 這裡模擬發送給原本專案的分析格式
        context = {"code": symbol, "raw_data": item['data'].to_dict()}
        result = analyzer.analyze(context)
        if result:
            final_reports.append(result)
            
    if final_reports:
        report_text = notifier.generate_dashboard_report(final_reports)
        notifier.send(report_text)
        logger.info("分析報告已發送！")

if __name__ == "__main__":
    main()
