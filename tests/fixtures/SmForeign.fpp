module Fixture {

  port Tick(context: U32)

  @ A C++ component defining a state machine of its own
  queued component Owner {
    sync input port tick: Tick

    state machine Inner {
      signal go
      initial enter A
      state A { on go enter A }
    }

    state machine instance own: Inner
  }

  @ A Python component instantiating the state machine another component defines
  @ fprime-python
  queued component PyForeign {
    sync input port tick: Tick
    state machine instance borrowed: Owner.Inner
  }

}
