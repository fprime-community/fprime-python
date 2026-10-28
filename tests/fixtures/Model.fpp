module Fixture {

  @ Port with a string argument
  port Text(msg: string size 16)

  @ Array of sized strings
  array Names = [3] string size 8

  @ Struct with a string member and an inline array of strings
  struct Record {
    label: string size 10
    tags: [2] string size 4
  }

  @ fprime-python
  passive component PyComp {
    sync input port textIn: Text
  }

  instance pyComp: PyComp base id 0x100

  @ fprime-python
  deployment topology Annotated {
    instance pyComp
  }

}
