@ Framework type aliases FPP requires of every model
constant FW_FIXED_LENGTH_STRING_SIZE = 256
type FwSizeStoreType = U16
type FwIndexType = I16
type FwSizeType = U64

type FwEventIdType = U32
type FwChanIdType = U32

@ Stand-ins for the framework ports that events and telemetry need
module Fw {
  type Time
  type LogBuffer
  type TlmBuffer
  enum LogSeverity { ACTIVITY_LO }
  port Log($id: FwEventIdType, ref timeTag: Fw.Time, $severity: LogSeverity, ref args: LogBuffer)
  port LogText($id: FwEventIdType, ref timeTag: Fw.Time, $severity: LogSeverity, ref $text: string size 256)
  port Time(ref $time: Fw.Time)
  port Tlm($id: FwChanIdType, ref timeTag: Fw.Time, ref val: TlmBuffer)
}
