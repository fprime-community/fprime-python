module Fixture {

  @ fprime-python
  passive component PyComp {
    sync input port textIn: Text
  }

  port Text(msg: string size 16)

  instance pyComp: PyComp base id 0x100

  deployment topology Unannotated {
    instance pyComp
  }

}
