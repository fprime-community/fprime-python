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

}
