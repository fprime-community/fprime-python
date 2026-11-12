module Fixture {

  port Tick(context: U32)

  @ An external state machine: its behavior is hand-written C++
  state machine Outside

  @ fprime-python
  queued component PyExternal {
    sync input port tick: Tick
    state machine instance ext: Outside
  }

}
