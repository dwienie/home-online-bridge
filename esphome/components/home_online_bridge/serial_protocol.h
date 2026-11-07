#pragma once
// Serial protocol of the Home Online controller. Header-only, no Arduino/ESPHome includes,
// so it can be unit tested natively (see esphome/tests/test_serial_protocol.cpp).
//
//   read : "s <id> <value>[%]\r"   id and value are at most 3 digits (0-999)
//   write: "S <id> <value>[%]\r\n"
//   'C' resets the parser, 'O' is the controller's handshake/heartbeat marker.
#include <cstdlib>
#include <string>

namespace home_online {

struct StateUpdate {
  int id;
  int value;
};

class LineParser {
 public:
  // Returns true when a complete, valid line was parsed into `out`.
  bool feed(char c, StateUpdate &out) {
    switch (c) {
      case 's':
        reset_();
        started_ = true;
        return false;
      case 'C':
        reset_();
        return false;
      case 'O':
        handshake_ = true;
        reset_();
        return false;
      case '%':
      case '\n':
        return false;
      case ' ':
        if (!started_) return false;
        if (field_ == 0) {
          field_ = 1;
        } else if (field_ == 1 && len_ > 0) {
          id_ = std::atoi(buf_);
          field_ = 2;
          len_ = 0;
        } else if (field_ == 2 && len_ > 0) {
          value_closed_ = true;  // a further digit would split the value ("6 0")
        }
        return false;
      case '\r': {
        bool ok = started_ && field_ == 2 && len_ > 0;
        if (ok) {
          buf_[len_] = '\0';
          out.id = id_;
          out.value = std::atoi(buf_);
        }
        reset_();
        return ok;
      }
      default:
        if (c >= '0' && c <= '9' && started_ && field_ >= 1 && len_ < 3 && !value_closed_) {
          buf_[len_++] = c;
          buf_[len_] = '\0';
        } else {
          reset_();  // letter, digit in the wrong place, or a 4th digit
        }
        return false;
    }
  }

  // True once for every 'O' received.
  bool take_handshake() {
    bool h = handshake_;
    handshake_ = false;
    return h;
  }

 private:
  void reset_() {
    started_ = false;
    value_closed_ = false;
    field_ = 0;
    len_ = 0;
    id_ = 0;
    buf_[0] = '\0';
  }

  bool started_{false};
  bool value_closed_{false};
  bool handshake_{false};
  int field_{0};  // 0 = before id, 1 = id, 2 = value
  int len_{0};
  int id_{0};
  char buf_[4]{};
};

inline std::string format_write(int id, int value, bool percent) {
  std::string s = "S " + std::to_string(id) + " " + std::to_string(value);
  if (percent) s += "%";
  return s;
}

// Any received byte is a beat. After 20 s of silence: 3 retries, then a re-handshake.
// `online()` follows real bytes only; the retry timer is separate so a silent controller stays offline.
class Liveness {
 public:
  enum Action { None, Retry, Rehandshake };

  explicit Liveness(unsigned long now = 0) : last_beat_(now), last_check_(now) {}

  // Start the retry timer without claiming the controller was heard (online() stays false until a beat).
  void start(unsigned long now) {
    last_check_ = now;
    last_beat_ = now - kTimeoutMs - 1;
    retries_ = 0;
  }

  void beat(unsigned long now) {
    last_beat_ = now;
    last_check_ = now;
    retries_ = 0;
  }

  Action check(unsigned long now) {
    if (now - last_check_ <= kTimeoutMs) return None;
    last_check_ = now;
    if (retries_ < kMaxRetries) {
      retries_++;
      return Retry;
    }
    retries_ = 0;
    return Rehandshake;
  }

  bool online(unsigned long now) const { return now - last_beat_ <= kTimeoutMs; }

 private:
  static constexpr unsigned long kTimeoutMs = 20000;
  static constexpr int kMaxRetries = 3;
  unsigned long last_beat_;
  unsigned long last_check_;
  int retries_{0};
};

}  // namespace home_online
