#include "home_online_bridge.h"

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome {
namespace home_online_bridge {

static const char *const TAG = "home_online_bridge";

void HomeOnlineBridge::setup() {
  this->liveness_.start(millis());
  this->handshake_();
}

// "o" then "O": the controller answers with 'O' and a dump of all slave states.
void HomeOnlineBridge::handshake_() {
  this->started_ = false;
  this->flush();
  this->write_str("o\r\n");
  this->write_str("O\r\n");
  ESP_LOGD(TAG, "handshake sent");
}

void HomeOnlineBridge::loop() {
  uint8_t c;
  while (this->available() && this->read_byte(&c)) {
    this->liveness_.beat(millis());
    home_online::StateUpdate update{0, 0};
    if (this->parser_.feed(static_cast<char>(c), update)) {
      this->publish_(update.id, update.value);
    }
    if (this->parser_.take_handshake()) {
      if (!this->started_) {
        this->started_ = true;  // handshake answered
      } else {
        this->write_str("\r\n");  // controller heartbeat, answered with an empty line
      }
    }
  }

  if (this->liveness_.check(millis()) == home_online::Liveness::Rehandshake) {
    ESP_LOGW(TAG, "controller silent, re-running handshake");
    this->handshake_();
  }
  this->replay_some_();
  if (this->online_ != nullptr) {
    this->online_->publish_state(this->liveness_.online(millis()));
  }
}

void HomeOnlineBridge::publish_(int id, int value) {
  this->cache_[id] = value;
  for (auto &cb : this->callbacks_) cb(id, value);
}

void HomeOnlineBridge::send(int id, int value, bool percent) {
  this->write_str(home_online::format_write(id, value, percent).c_str());
  this->write_str("\r\n");
}

void HomeOnlineBridge::send_raw(const std::string &line) {
  this->write_str(line.c_str());
  this->write_str("\r\n");
}

// Queue every cached state; loop() drains it a few at a time so a reconnect does not flood the API.
void HomeOnlineBridge::resync() {
  this->resync_queue_.clear();
  for (auto &kv : this->cache_) this->resync_queue_.push_back(kv.first);
  this->resync_pos_ = 0;
}

void HomeOnlineBridge::replay_some_() {
  for (size_t n = 0; n < kReplayPerLoop && this->resync_pos_ < this->resync_queue_.size(); n++) {
    int id = this->resync_queue_[this->resync_pos_++];
    auto it = this->cache_.find(id);
    if (it == this->cache_.end()) continue;
    for (auto &cb : this->callbacks_) cb(id, it->second);
  }
}

}  // namespace home_online_bridge
}  // namespace esphome
