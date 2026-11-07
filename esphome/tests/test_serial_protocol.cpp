// Native test for the serial protocol. Build and run:
//   g++ -std=c++17 -I../components/home_online_bridge test_serial_protocol.cpp -o t && ./t
#include <cstdio>
#include <string>

#include "serial_protocol.h"

using namespace home_online;

static int failures = 0;
#define CHECK(cond)                                                    \
  do {                                                                 \
    if (!(cond)) {                                                     \
      std::printf("FAIL line %d: %s\n", __LINE__, #cond);              \
      failures++;                                                      \
    }                                                                  \
  } while (0)

// Feed a whole string, collect emitted updates.
static int feed_all(LineParser &p, const std::string &s, StateUpdate *last = nullptr) {
  int emitted = 0;
  StateUpdate u{-1, -1};
  for (char c : s) {
    StateUpdate out{-1, -1};
    if (p.feed(c, out)) {
      emitted++;
      u = out;
    }
  }
  if (last != nullptr) *last = u;
  return emitted;
}

int main() {
  {  // basic line, percent ignored
    LineParser p;
    StateUpdate u;
    CHECK(feed_all(p, "s 279 60%\r", &u) == 1);
    CHECK(u.id == 279 && u.value == 60);
  }
  {  // no range filter: ID 59 works
    LineParser p;
    StateUpdate u;
    CHECK(feed_all(p, "s 59 1\r", &u) == 1);
    CHECK(u.id == 59 && u.value == 1);
  }
  {  // byte-by-byte equals whole-string, and two lines in a row
    LineParser p;
    StateUpdate u;
    CHECK(feed_all(p, "s 1", &u) == 0);
    CHECK(feed_all(p, "55 ", &u) == 0);
    CHECK(feed_all(p, "1\r", &u) == 1);
    CHECK(u.id == 155 && u.value == 1);
    CHECK(feed_all(p, "s 156 0\rs 157 1\r", &u) == 2);
    CHECK(u.id == 157 && u.value == 1);
  }
  {  // non-numeric and too-long fields emit nothing
    LineParser p;
    CHECK(feed_all(p, "s 12 abc\r") == 0);
    CHECK(feed_all(p, "s 12 1000\r") == 0);
    CHECK(feed_all(p, "s 1234 5\r") == 0);
    CHECK(feed_all(p, "s 12\r") == 0);
    StateUpdate u;
    CHECK(feed_all(p, "s 12 5\r", &u) == 1);  // parser recovered
    CHECK(u.id == 12 && u.value == 5);
  }
  {  // a value split by a space is rejected, but a trailing space is tolerated (old parser did)
    LineParser p;
    StateUpdate u;
    CHECK(feed_all(p, "s 279 6 0\r") == 0);
    CHECK(feed_all(p, "s 279 60 \r", &u) == 1);
    CHECK(u.id == 279 && u.value == 60);
    CHECK(feed_all(p, "s 279  7\r", &u) == 1);  // extra space before the value is fine
    CHECK(u.id == 279 && u.value == 7);
  }
  {  // 'C' resets mid line, LF alone is ignored, garbage before 's' is ignored
    LineParser p;
    StateUpdate u;
    CHECK(feed_all(p, "s 12 5C", &u) == 0);
    CHECK(feed_all(p, "\r", &u) == 0);
    CHECK(feed_all(p, "xyz\n s 20 7\r\n", &u) == 1);
    CHECK(u.id == 20 && u.value == 7);
  }
  {  // 'O' sets handshake flag once
    LineParser p;
    CHECK(!p.take_handshake());
    feed_all(p, "O");
    CHECK(p.take_handshake());
    CHECK(!p.take_handshake());
  }
  {  // write format
    CHECK(format_write(279, 60, true) == "S 279 60%");
    CHECK(format_write(82, 1, false) == "S 82 1");
  }
  {  // liveness: 3 retries then rehandshake; a beat resets
    Liveness l(0);
    CHECK(l.check(19999) == Liveness::None);
    CHECK(l.check(20001) == Liveness::Retry);
    CHECK(l.check(40002) == Liveness::Retry);
    CHECK(l.check(60003) == Liveness::Retry);
    CHECK(l.check(80004) == Liveness::Rehandshake);
    CHECK(l.check(80005) == Liveness::None);
    l.beat(100000);
    CHECK(l.check(110000) == Liveness::None);
    CHECK(l.check(120001) == Liveness::Retry);
    l.beat(120002);
    CHECK(l.check(140003) == Liveness::Retry);  // retry count was reset by the beat
  }
  {  // online() is driven by real bytes only: retries must not make a silent controller look online
    Liveness l(0);
    l.start(1000);
    CHECK(!l.online(1000));  // nothing heard yet
    l.beat(2000);
    CHECK(l.online(2000));
    CHECK(l.online(22000));
    CHECK(!l.online(22001));
    CHECK(l.check(22001) == Liveness::Retry);
    CHECK(!l.online(22001));  // the retry timer does not revive it
    CHECK(l.check(42002) == Liveness::Retry);
    CHECK(l.check(62003) == Liveness::Retry);
    CHECK(l.check(82004) == Liveness::Rehandshake);
    CHECK(!l.online(82004));
    l.beat(82005);
    CHECK(l.online(82005));
  }
  if (failures == 0) std::printf("all passed\n");
  return failures == 0 ? 0 : 1;
}
