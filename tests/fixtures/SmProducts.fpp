module Fw {
  port DpGet()
  port DpSend()
}

module Fixture {

  port Tick(context: U32)

  @ A Python component with data products
  @ fprime-python
  active component PyProducts {
    async input port tick: Tick

    product get port productGetOut
    product send port productSendOut
    time get port timeGetOut

    product record reading: U32 id 0
    product container readings id 0
  }

}
