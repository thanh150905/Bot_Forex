/*
 * ForexBot C++ Core
 * - Xác thực license với server qua HTTP (libcurl)
 * - Giao tiếp với MT4/MT5 EA qua Named Pipe (Windows)
 * - Strategy engine cơ bản (EMA crossover + ATR filter)
 *
 * Compile: g++ -std=c++17 -O2 bot_core.cpp -lcurl -o forex_bot
 * Windows: cần link ws2_32, libcurl
 */

#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <mutex>
#include <atomic>
#include <sstream>
#include <ctime>

// HTTP (libcurl) - cài: sudo apt install libcurl4-openssl-dev
#include <curl/curl.h>

// Windows Named Pipe
#ifdef _WIN32
#include <windows.h>
#endif

// JSON đơn giản (không dùng thư viện nặng)
#include "json_simple.hpp"  // xem file kế tiếp


// ─── Config ──────────────────────────────────────────────────────────────────

struct Config {
    std::string server_url    = "http://your-server.com:8000";
    std::string license_key   = "YOUR_LICENSE_KEY_HERE";
    std::string mt_account    = "12345678";
    std::string pipe_name     = "\\\\.\\pipe\\ForexBotPipe";
    int         ping_interval = 300;  // giây
};

// ─── Globals ─────────────────────────────────────────────────────────────────

Config          g_config;
std::string     g_bot_token;
std::mutex      g_token_mutex;
std::atomic<bool> g_running{true};

#ifdef _WIN32
HANDLE g_pipe = INVALID_HANDLE_VALUE;
#endif


// ─── HTTP Helper ─────────────────────────────────────────────────────────────

static size_t write_cb(char* ptr, size_t size, size_t nmemb, std::string* data) {
    data->append(ptr, size * nmemb);
    return size * nmemb;
}

struct HttpResponse {
    long        status_code = 0;
    std::string body;
};

HttpResponse http_post(const std::string& url, const std::string& json_body,
                       const std::string& bearer_token = "") {
    HttpResponse resp;
    CURL* curl = curl_easy_init();
    if (!curl) return resp;

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    if (!bearer_token.empty()) {
        std::string auth = "Authorization: Bearer " + bearer_token;
        headers = curl_slist_append(headers, auth.c_str());
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &resp.body);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);

    curl_easy_perform(curl);
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &resp.status_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    return resp;
}


// ─── License Verification ────────────────────────────────────────────────────

bool verify_license() {
    std::string body = R"({"license_key":")" + g_config.license_key
                     + R"(","mt_account":")" + g_config.mt_account + R"("})";

    auto resp = http_post(g_config.server_url + "/bot/verify", body);

    if (resp.status_code == 200) {
        // Parse token từ JSON response
        std::string token = json_extract(resp.body, "bot_token");
        if (!token.empty()) {
            std::lock_guard<std::mutex> lock(g_token_mutex);
            g_bot_token = token;
            std::cout << "[LICENSE] ✅ Xác thực thành công\n";
            return true;
        }
    }

    std::cout << "[LICENSE] ❌ Xác thực thất bại [" << resp.status_code << "]: "
              << resp.body << "\n";
    return false;
}

void ping_loop() {
    int fail_count = 0;
    while (g_running) {
        std::this_thread::sleep_for(std::chrono::seconds(g_config.ping_interval));

        std::string token;
        {
            std::lock_guard<std::mutex> lock(g_token_mutex);
            token = g_bot_token;
        }

        std::string body = R"({"bot_token":")" + token
                         + R"(","license_key":")" + g_config.license_key + R"("})";
        auto resp = http_post(g_config.server_url + "/bot/ping", body);

        if (resp.status_code == 200) {
            std::string new_token = json_extract(resp.body, "bot_token");
            if (!new_token.empty()) {
                std::lock_guard<std::mutex> lock(g_token_mutex);
                g_bot_token = new_token;
            }
            fail_count = 0;
            std::cout << "[LICENSE] Ping OK\n";
        } else {
            fail_count++;
            std::cerr << "[LICENSE] ⚠️ Ping thất bại lần " << fail_count << "\n";
            if (fail_count >= 3) {
                std::cerr << "[LICENSE] ❌ Mất kết nối server. Dừng bot.\n";
                g_running = false;
                std::exit(1);
            }
        }
    }
}


// ─── Named Pipe (Windows) ────────────────────────────────────────────────────

#ifdef _WIN32

bool create_pipe() {
    g_pipe = CreateNamedPipeA(
        g_config.pipe_name.c_str(),
        PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
        1,          // max instances
        4096,       // out buffer
        4096,       // in buffer
        0,          // timeout
        nullptr
    );

    if (g_pipe == INVALID_HANDLE_VALUE) {
        std::cerr << "[PIPE] Lỗi tạo pipe: " << GetLastError() << "\n";
        return false;
    }

    std::cout << "[PIPE] ✅ Named Pipe tạo OK: " << g_config.pipe_name << "\n";
    std::cout << "[PIPE] Đang chờ MT4/MT5 EA kết nối...\n";

    // Chờ EA kết nối
    ConnectNamedPipe(g_pipe, nullptr);
    std::cout << "[PIPE] ✅ EA đã kết nối!\n";
    return true;
}

bool send_command(const std::string& cmd) {
    if (g_pipe == INVALID_HANDLE_VALUE) return false;
    DWORD written;
    std::string msg = cmd + "\n";
    bool ok = WriteFile(g_pipe, msg.c_str(), msg.size(), &written, nullptr);
    if (ok) std::cout << "[PIPE] Gửi: " << cmd << "\n";
    else    std::cerr << "[PIPE] Lỗi gửi: " << GetLastError() << "\n";
    return ok;
}

#else  // Linux/Mac stub (cho testing)

bool create_pipe() {
    std::cout << "[PIPE] Stub mode (không phải Windows)\n";
    return true;
}

bool send_command(const std::string& cmd) {
    std::cout << "[PIPE] Lệnh (stub): " << cmd << "\n";
    return true;
}

#endif


// ─── Report Trade to Server ──────────────────────────────────────────────────

void report_trade(const std::string& ticket, const std::string& symbol,
                  const std::string& direction, double entry, double lot,
                  double sl, double tp, const std::string& status = "open",
                  double close_price = 0, double profit = 0, double pips = 0) {
    std::string token;
    {
        std::lock_guard<std::mutex> lock(g_token_mutex);
        token = g_bot_token;
    }

    std::ostringstream oss;
    oss << "{"
        << "\"bot_token\":\"" << token << "\","
        << "\"license_key\":\"" << g_config.license_key << "\","
        << "\"ticket\":\"" << ticket << "\","
        << "\"symbol\":\"" << symbol << "\","
        << "\"direction\":\"" << direction << "\","
        << "\"entry_price\":" << entry << ","
        << "\"sl_price\":" << sl << ","
        << "\"tp_price\":" << tp << ","
        << "\"lot_size\":" << lot << ","
        << "\"status\":\"" << status << "\","
        << "\"close_price\":" << close_price << ","
        << "\"profit\":" << profit << ","
        << "\"pips\":" << pips
        << "}";

    http_post(g_config.server_url + "/bot/report-trade", oss.str());
}


// ─── Strategy Engine (EMA Crossover + ATR Filter) ────────────────────────────

struct Bar {
    double open, high, low, close;
    time_t time;
};

// Tính EMA
double calc_ema(const std::vector<double>& prices, int period) {
    if (prices.size() < (size_t)period) return 0;
    double k = 2.0 / (period + 1);
    double ema = prices[0];
    for (size_t i = 1; i < prices.size(); i++)
        ema = prices[i] * k + ema * (1 - k);
    return ema;
}

// Tính ATR (Average True Range)
double calc_atr(const std::vector<Bar>& bars, int period) {
    if (bars.size() < (size_t)period + 1) return 0;
    double atr = 0;
    for (int i = bars.size() - period; i < (int)bars.size(); i++) {
        double tr = std::max({
            bars[i].high - bars[i].low,
            std::abs(bars[i].high - bars[i-1].close),
            std::abs(bars[i].low  - bars[i-1].close)
        });
        atr += tr;
    }
    return atr / period;
}

enum Signal { NONE, BUY_SIGNAL, SELL_SIGNAL };

/*
 * Logic chiến lược cơ bản:
 *   - EMA 8 cắt lên EMA 21 → BUY
 *   - EMA 8 cắt xuống EMA 21 → SELL
 *   - ATR > threshold → thị trường có biến động đủ lớn để vào
 *   - Lọc xu hướng bằng EMA 50 (chỉ buy khi giá trên EMA50, sell khi dưới)
 *
 * Bạn sẽ tích hợp thêm AI signal từ Python server ở đây.
 */
Signal analyze_market(const std::vector<Bar>& bars) {
    if (bars.size() < 55) return NONE;

    std::vector<double> closes;
    for (auto& b : bars) closes.push_back(b.close);

    // EMA ngắn và dài
    std::vector<double> closes_8(closes.end()  - 8,  closes.end());
    std::vector<double> closes_21(closes.end() - 21, closes.end());
    std::vector<double> closes_50(closes.end() - 50, closes.end());
    std::vector<double> closes_8_prev(closes.end()  - 9,  closes.end() - 1);
    std::vector<double> closes_21_prev(closes.end() - 22, closes.end() - 1);

    double ema8_curr  = calc_ema(closes_8,      8);
    double ema21_curr = calc_ema(closes_21,     21);
    double ema50      = calc_ema(closes_50,     50);
    double ema8_prev  = calc_ema(closes_8_prev, 8);
    double ema21_prev = calc_ema(closes_21_prev,21);
    double atr        = calc_atr(bars,          14);
    double price      = bars.back().close;

    // ATR filter: bỏ qua khi thị trường quá yên (ranging không rõ)
    double min_atr = price * 0.0003;  // 3 pips EURUSD
    if (atr < min_atr) return NONE;

    // EMA crossover
    bool cross_up   = (ema8_prev <= ema21_prev) && (ema8_curr > ema21_curr);
    bool cross_down = (ema8_prev >= ema21_prev) && (ema8_curr < ema21_curr);

    // Trend filter
    bool uptrend   = price > ema50;
    bool downtrend = price < ema50;

    if (cross_up   && uptrend)   return BUY_SIGNAL;
    if (cross_down && downtrend) return SELL_SIGNAL;
    return NONE;
}


// ─── Main ────────────────────────────────────────────────────────────────────

int main() {
    std::cout << "=== ForexBot C++ Core v1.0 ===\n";

    // Đọc config từ env vars hoặc file
    if (const char* lk = std::getenv("LICENSE_KEY"))  g_config.license_key = lk;
    if (const char* sv = std::getenv("SERVER_URL"))   g_config.server_url  = sv;
    if (const char* mt = std::getenv("MT_ACCOUNT"))   g_config.mt_account  = mt;

    // 1. Xác thực license
    if (!verify_license()) {
        std::cerr << "[MAIN] Không thể xác thực. Thoát.\n";
        return 1;
    }

    // 2. Tạo pipe kết nối với MT4/MT5 EA
    if (!create_pipe()) {
        std::cerr << "[MAIN] Lỗi tạo pipe. Thoát.\n";
        return 1;
    }

    // 3. Bắt đầu ping thread
    std::thread ping_thread(ping_loop);

    // 4. Main loop: phân tích và gửi lệnh
    std::cout << "[MAIN] Bot bắt đầu phân tích thị trường...\n";

    while (g_running) {
        // TODO: Lấy dữ liệu OHLCV từ MT4/MT5 hoặc broker API
        // Ví dụ: std::vector<Bar> bars = fetch_bars("EURUSD", TIMEFRAME_M15, 100);
        // Signal sig = analyze_market(bars);

        // Ví dụ demo gửi lệnh BUY:
        // if (sig == BUY_SIGNAL) {
        //     double entry = bars.back().close;
        //     double atr   = calc_atr(bars, 14);
        //     double sl    = entry - atr * 1.5;
        //     double tp    = entry + atr * 2.0;
        //     send_command("BUY|EURUSD|0.1|" + std::to_string(sl) + "|" + std::to_string(tp) + "|0");
        //     report_trade("10001", "EURUSD", "BUY", entry, 0.1, sl, tp);
        // }

        std::this_thread::sleep_for(std::chrono::seconds(15));
    }

    ping_thread.join();
    return 0;
}
