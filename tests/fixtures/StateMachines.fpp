module Fixture {

  @ Port driving the state machines
  port Tick(context: U32)

  @ An internal state machine shared by every component below
  state machine Blinker {
    action store: U32
    action reset
    guard allow: U32
    signal advance: U32
    signal back
    signal rename: string size 8
    initial do { reset } enter IDLE
    state IDLE {
      on advance if allow do { store } enter BUSY
      on rename enter IDLE
    }
    state BUSY {
      on back do { reset } enter IDLE
    }
  }

  @ An external state machine, which no Python component may instantiate
  state machine Outside

  @ A component instantiating one state machine twice and defining another
  @ fprime-python
  queued component PySm {
    sync input port tick: Tick

    @ A state machine defined inside the component
    state machine Local {
      action note
      signal go
      initial enter X
      state X {
        on go do { note } enter Y
      }
      state Y
    }

    state machine instance first: Blinker priority 1 assert
    state machine instance second: Blinker priority 2 drop
    state machine instance loc: Local
  }

  @ A second component sharing the Blinker state machine
  @ fprime-python
  active component PyShared {
    async input port tick: Tick
    state machine instance only: Blinker
  }

  @ An alias of a primitive type, which a state machine passes by const reference
  type Count = U32

  @ An enumeration carried by a signal
  enum Mode { ON, OFF }

  @ A structure carried by a signal
  struct Pair { left: U32, right: U32 }

  @ A state machine whose signals carry every kind of value, with a nested state and a choice
  state machine Wide {
    action onCount: Count
    action onMode: Mode
    action onPair: Pair
    action onLabel: string
    guard checkCount: Count
    guard checkMode: Mode
    signal count: Count
    signal mode: Mode
    signal pair: Pair
    signal label: string
    signal hop
    initial enter OUTER
    state OUTER {
      initial enter INNER
      state INNER {
        on count do { onCount } enter DECIDE
        on label do { onLabel }
      }
      on pair do { onPair } enter OUTER
    }
    choice DECIDE { if checkCount enter OUTER else enter LAST }
    state LAST {
      on mode if checkMode do { onMode } enter OUTER
      on hop enter LAST
    }
  }

  @ A component instantiating the wide state machine with 'block' queue-full behavior
  @ fprime-python
  queued component PyWide {
    sync input port tick: Tick

    @ An external state machine defined but never instantiated, so nothing binds it
    state machine Hidden

    state machine instance wide: Wide priority 1 block
  }

}
