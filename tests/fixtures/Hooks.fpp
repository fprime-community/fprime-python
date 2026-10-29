module Fixture {

  @ Port with a string argument
  port Text(note: string size 16)

  @ A component asking for an overflow hook on every member that can have one
  @ fprime-python
  queued component PyHooks {
    async input port textIn: Text hook
    async input port dropIn: Text drop
    internal port poke(note: string size 5) hook
    async command DO(n: U32) hook
    async command PLAIN
    command recv port cmdIn
    command reg port cmdRegOut
    command resp port cmdResponseOut
  }

}
