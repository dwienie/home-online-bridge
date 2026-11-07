#pragma once

#include <functional>
#include <map>
#include <string>
#include <vector>

#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/uart/uart.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "serial_protocol.h"

namespace esphome {
namespace home_online_bridge {

class HomeOnlineBridge : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  float get_setup_priority() const override { return setup_priority::LATE; }

  void set_online_sensor(binary_sensor::BinarySensor *sensor) { this->online_ = sensor; }
  void add_on_state_callback(std::function<void(int, int)> &&cb) { this->callbacks_.push_back(std::move(cb)); }

  // Exposed to Home Assistant as API actions (see home-online-bridge.yaml).
  void send(int id, int value, bool percent);
  void send_raw(const std::string &line);
  void resync();  // replay cached states as events (paced); does not touch the controller

 protected:
  void handshake_();
  void publish_(int id, int value);
  void replay_some_();

  static constexpr size_t kReplayPerLoop = 8;

  home_online::LineParser parser_;
  home_online::Liveness liveness_;
  std::map<int, int> cache_;
  std::vector<int> resync_queue_;
  size_t resync_pos_{0};
  std::vector<std::function<void(int, int)>> callbacks_;
  binary_sensor::BinarySensor *online_{nullptr};
  bool started_{false};  // first 'O' after the handshake seen
  bool open_pending_{false};  // 'o' sent, 'O' follows after kHandshakeGapMs
  unsigned long open_at_{0};
  static constexpr unsigned long kHandshakeGapMs = 500;
};

class StateTrigger : public Trigger<int, int> {
 public:
  explicit StateTrigger(HomeOnlineBridge *parent) {
    parent->add_on_state_callback([this](int id, int value) { this->trigger(id, value); });
  }
};

}  // namespace home_online_bridge
}  // namespace esphome
