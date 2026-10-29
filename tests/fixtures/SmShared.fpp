module Fixture {

  @ A component instantiating a state machine another module defines
  @ fprime-python
  active component PyElsewhere {
    async input port tick: Tick
    state machine instance remote: Blinker
  }

}
