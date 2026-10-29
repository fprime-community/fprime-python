module Fixture {

  port Tick(context: U32)

  state machine Toggle {
    signal flip
    initial enter OFF
    state OFF {
      on flip enter ON
    }
    state ON {
      on flip enter OFF
    }
  }

  @ fprime-python
  queued component PySmHook {
    sync input port tick: Tick
    state machine instance toggle: Toggle hook
  }

}
