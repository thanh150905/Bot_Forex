/*
 * json_simple.hpp - Parse JSON key:value đơn giản không cần thư viện
 * Dùng cho C++ bot core
 */

#pragma once
#include <string>
#include <cstddef>

// Trích xuất giá trị string từ JSON: "key":"value"
inline std::string json_extract(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\":\"";
    size_t start = json.find(search);
    if (start == std::string::npos) return "";
    start += search.size();
    size_t end = json.find("\"", start);
    if (end == std::string::npos) return "";
    return json.substr(start, end - start);
}

// Trích xuất giá trị số từ JSON: "key":value
inline std::string json_extract_num(const std::string& json, const std::string& key) {
    std::string search = "\"" + key + "\":";
    size_t start = json.find(search);
    if (start == std::string::npos) return "";
    start += search.size();
    size_t end = json.find_first_of(",}", start);
    if (end == std::string::npos) return "";
    return json.substr(start, end - start);
}
