//+------------------------------------------------------------------+
//| ForexBot_EA.mq5                                                  |
//| Expert Advisor: Nhận lệnh từ C++ bot qua Named Pipe             |
//| Hỗ trợ: Verify license qua HTTP, nhận BUY/SELL/CLOSE            |
//+------------------------------------------------------------------+
#property copyright "Your Name"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade         trade;
CPositionInfo  posInfo;

//--- Input parameters
input string   LICENSE_KEY      = "YOUR_LICENSE_KEY";       // License key
input string   SERVER_URL       = "http://your-server:8000"; // License server URL
input string   PIPE_NAME        = "\\\\.\\pipe\\ForexBotPipe"; // Named pipe
input double   DEFAULT_LOT      = 0.01;
input int      SLIPPAGE         = 10;
input bool     ENABLE_LOGGING   = true;

//--- Globals
int      g_pipe_handle    = INVALID_HANDLE;
string   g_bot_token      = "";
bool     g_verified       = false;
datetime g_last_verify    = 0;
int      g_verify_interval = 21600; // 6 giờ (giây)

//+------------------------------------------------------------------+
void OnInit()
{
   trade.SetDeviationInPoints(SLIPPAGE);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   Log("=== ForexBot EA khởi động ===");
   Log("License: " + StringSubstr(LICENSE_KEY, 0, 8) + "...");

   // Xác thực license lần đầu
   if(!VerifyLicense()) {
      Log("❌ Xác thực thất bại. EA dừng.");
      ExpertRemove();
      return;
   }

   // Mở pipe kết nối với C++ bot
   OpenPipe();
   EventSetTimer(5);  // Check pipe mỗi 5 giây
   Log("✅ EA sẵn sàng nhận lệnh từ C++ bot");
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_pipe_handle != INVALID_HANDLE)
      FileClose(g_pipe_handle);
   Log("EA đã dừng. Lý do: " + string(reason));
}

//+------------------------------------------------------------------+
void OnTimer()
{
   // 1. Xác thực lại license định kỳ
   if(TimeCurrent() - g_last_verify >= g_verify_interval) {
      if(!VerifyLicense()) {
         Log("❌ Xác thực định kỳ thất bại. EA dừng.");
         ExpertRemove();
         return;
      }
   }

   // 2. Đọc lệnh từ pipe
   ReadPipeCommands();
}

//+------------------------------------------------------------------+
void OnTick()
{
   // Có thể thêm logic trailing stop ở đây
}

//+------------------------------------------------------------------+
bool VerifyLicense()
{
   string url     = SERVER_URL + "/bot/verify";
   string headers = "Content-Type: application/json\r\n";
   string body    = "{\"license_key\":\"" + LICENSE_KEY + "\","
                  + "\"mt_account\":\"" + string(AccountInfoInteger(ACCOUNT_LOGIN)) + "\"}";
   char   req[], res[];
   string resp_headers;

   StringToCharArray(body, req, 0, StringLen(body));
   int result = WebRequest("POST", url, headers, 10000, req, res, resp_headers);

   if(result == 200) {
      string response = CharArrayToString(res);
      g_bot_token  = ExtractJson(response, "bot_token");
      g_last_verify = TimeCurrent();
      g_verified   = true;
      Log("✅ License hợp lệ | Token: " + StringSubstr(g_bot_token, 0, 16) + "...");
      return true;
   } else {
      string response = CharArrayToString(res);
      Log("❌ Verify thất bại [HTTP " + string(result) + "]: " + response);
      g_verified = false;
      return false;
   }
}

//+------------------------------------------------------------------+
void OpenPipe()
{
   // Named pipe: C++ bot ghi vào, EA đọc ra
   g_pipe_handle = FileOpen(PIPE_NAME, FILE_READ | FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(g_pipe_handle == INVALID_HANDLE) {
      Log("⚠️ Chưa mở được pipe (C++ bot chưa tạo). Sẽ thử lại...");
   } else {
      Log("✅ Pipe kết nối OK: " + PIPE_NAME);
   }
}

//+------------------------------------------------------------------+
void ReadPipeCommands()
{
   if(g_pipe_handle == INVALID_HANDLE) {
      OpenPipe();  // thử lại
      return;
   }

   while(FileIsExist(PIPE_NAME, FILE_COMMON) && !FileIsEnding(g_pipe_handle)) {
      string cmd = FileReadString(g_pipe_handle);
      if(StringLen(cmd) == 0) break;
      cmd = StringTrimRight(StringTrimLeft(cmd));
      Log("📨 Nhận lệnh: " + cmd);
      ProcessCommand(cmd);
   }
}

//+------------------------------------------------------------------+
void ProcessCommand(string cmd)
{
   // Format: ACTION|SYMBOL|LOT|SL|TP|TICKET
   // Ví dụ: "BUY|EURUSD|0.1|1.0820|1.0920|0"
   //        "SELL|XAUUSD|0.05|1950.0|1930.0|0"
   //        "CLOSE|EURUSD|0|0|0|10001"
   //        "CLOSE_ALL||0|0|0|0"

   string parts[];
   int count = StringSplit(cmd, '|', parts);
   if(count < 1) return;

   string action = parts[0];

   if(action == "BUY" && count >= 5) {
      string symbol = parts[1];
      double lot    = StringToDouble(parts[2]);
      double sl     = StringToDouble(parts[3]);
      double tp     = StringToDouble(parts[4]);
      OpenOrder(ORDER_TYPE_BUY, symbol, lot, sl, tp);
   }
   else if(action == "SELL" && count >= 5) {
      string symbol = parts[1];
      double lot    = StringToDouble(parts[2]);
      double sl     = StringToDouble(parts[3]);
      double tp     = StringToDouble(parts[4]);
      OpenOrder(ORDER_TYPE_SELL, symbol, lot, sl, tp);
   }
   else if(action == "CLOSE" && count >= 6) {
      ulong ticket = StringToInteger(parts[5]);
      CloseOrder(ticket);
   }
   else if(action == "CLOSE_ALL") {
      CloseAllOrders();
   }
   else if(action == "MODIFY" && count >= 6) {
      ulong  ticket = StringToInteger(parts[5]);
      double sl     = StringToDouble(parts[3]);
      double tp     = StringToDouble(parts[4]);
      ModifyOrder(ticket, sl, tp);
   }
   else {
      Log("⚠️ Lệnh không nhận ra: " + cmd);
   }
}

//+------------------------------------------------------------------+
void OpenOrder(ENUM_ORDER_TYPE type, string symbol, double lot, double sl, double tp)
{
   if(!g_verified) {
      Log("❌ Chưa xác thực license, không mở lệnh");
      return;
   }

   double price = (type == ORDER_TYPE_BUY)
                ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                : SymbolInfoDouble(symbol, SYMBOL_BID);

   bool ok = trade.PositionOpen(symbol, type, lot, price, sl, tp, "ForexBot");
   if(ok) {
      ulong ticket = trade.ResultOrder();
      string dir   = (type == ORDER_TYPE_BUY) ? "BUY" : "SELL";
      Log("✅ Mở lệnh " + dir + " " + symbol + " Lot:" + string(lot)
          + " Entry:" + string(price) + " SL:" + string(sl) + " TP:" + string(tp)
          + " Ticket:#" + string(ticket));
   } else {
      Log("❌ Mở lệnh thất bại: " + trade.ResultComment());
   }
}

//+------------------------------------------------------------------+
void CloseOrder(ulong ticket)
{
   if(posInfo.SelectByTicket(ticket)) {
      bool ok = trade.PositionClose(ticket);
      if(ok)
         Log("✅ Đóng lệnh #" + string(ticket) + " OK");
      else
         Log("❌ Đóng lệnh thất bại: " + trade.ResultComment());
   } else {
      Log("⚠️ Không tìm thấy lệnh #" + string(ticket));
   }
}

//+------------------------------------------------------------------+
void CloseAllOrders()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(posInfo.SelectByIndex(i)) {
         trade.PositionClose(posInfo.Ticket());
      }
   }
   Log("✅ Đã đóng tất cả lệnh");
}

//+------------------------------------------------------------------+
void ModifyOrder(ulong ticket, double sl, double tp)
{
   bool ok = trade.PositionModify(ticket, sl, tp);
   if(ok)
      Log("✅ Sửa lệnh #" + string(ticket) + " SL:" + string(sl) + " TP:" + string(tp));
   else
      Log("❌ Sửa lệnh thất bại: " + trade.ResultComment());
}

//+------------------------------------------------------------------+
string ExtractJson(string json, string key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

//+------------------------------------------------------------------+
void Log(string msg)
{
   if(ENABLE_LOGGING)
      PrintFormat("[ForexBot EA] %s | %s", TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES), msg);
}
