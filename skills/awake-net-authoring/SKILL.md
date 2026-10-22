---
name: awake-net-authoring
description: >
  Author multiplayer game protocols, binary packets, and authoritative Ktor game servers on
  :awake:net:api and :awake:net:server-ktor. Use before adding network messages, packet codecs,
  opcodes, Protobuf/JSON payloads, WebSocket sessions, or GameServerHost features.
license: Apache-2.0
metadata:
  author: awake
  last-updated: '2026-10-22'
  keywords: Awake net, PacketFormat, PacketOpcodeRegistry, PacketWriter, PacketReader, Protobuf, GameServerHost, GameFeature, MessageRouter, NetId, NetViolation
---

# Awake Multiplayer & Packet Authoring

This skill governs how games and plugins built on Awake declare network protocols, choose wire formats,
and wire authoritative Ktor servers using `:awake:net:api` (`com.awakekt.awake.net`) and
`:awake:net:server-ktor` (`com.awakekt.awake.net.server`).

## 1. Pick the wire format by channel (never one format for everything)

Multiplayer games have four distinct data planes with different bandwidth, security, and schema-evolution needs:

| Channel / Data Plane | Format | When to use |
|---|---|---|
| **1. Handshake, Lobby & Admin HTTP** | `kotlinx-serialization-json` (`Json`) | Human-readable REST endpoints, room lists, health checks, and RFC 9457 error responses off the tick path. |
| **2. Evolving, Persisted, or Cross-Service Data** | `kotlinx-serialization-protobuf` (`ProtoBuf`) | **Use Protobuf** when **schema evolution** (`@ProtoNumber` optional/new fields across rolling upgrades), **database/replay persistence**, or **non-Kotlin tooling** (Python/Go/Rust/C++) is required. Do **not** use stock `ProtoBuf` directly on untrusted real-time tick sockets, as it adds field-tag overhead, lacks millimetre float quantization, and does not enforce per-field pre-allocation string/collection caps during decode. |
| **3. Standard Client $\leftrightarrow$ Server Game Packets** | `PacketFormat` + `PacketOpcodeRegistry` (`:awake:net:api`) | **Default for game messages** (chat, party, guild, inventory, trade, skills, quests, dialogs). Zero manual `write*`/`read*` code, tagless VarInt/ZigZag wire layout, and declarative **pre-allocation DoS bounds**. |
| **4. 20–60 Hz Tick Hot Path** | Direct `PacketWriter` / `PacketReader` | Bit-packed movement `Input` and entity `Snapshot` deltas (sub-byte bitflags, conditional fields, zero per-tick allocations). Coexists on the same `PacketWriter`/`PacketReader` as `PacketOpcodeRegistry`. |

Because both `ProtoBuf` and `PacketFormat` implement `kotlinx.serialization.BinaryFormat`, the **same `@Serializable data class`** can be encoded with `PacketFormat` on the live game wire and `ProtoBuf` for persistence or cross-service RPC.

---

## 2. Declare packets with `@Serializable` and `@Packet*` bounds annotations

Never grow a monolithic `when (message)` codec with manual `writeVarInt`/`readVarInt` calls for standard messages. Annotate the `@Serializable` message properties with `:awake:net:api` bounds and quantization annotations:

- `@PacketMaxBytes(max, nonEmpty = false, nonBlank = false)` — enforces UTF-8 byte ceiling **before** allocating a `ByteArray`/`String` on decode, and rejects oversized strings on encode.
- `@PacketCollectionSize(min = 0, max, fixed = false)` — validates list/map element count **before** allocating the collection (`fixed = true` omits the wire count varint for fixed-length tuples).
- `@PacketIntRange(min, max, clampOnEncode = true, bitMask = 0, byteWire = false)` — clamps or validates `Int` ranges (`byteWire = true` writes a single byte instead of a VarInt).
- `@PacketLongRange(min, max, clampOnEncode = true)` — clamps or validates `Long` VarLong ranges.
- `@PacketMillis(unsigned = false)` — quantizes `Float` metres/radians to whole millimetres/milliradians (`roundToInt(v * 1000f)`) as ZigZag (signed) or VarInt (unsigned) so no raw IEEE-754 `NaN`/`Infinity` floats cross the wire.
- `@PacketEmptyNull` — encodes `String?` without a boolean presence byte by mapping `null` $\leftrightarrow$ `""`.
- `@PacketZeroNullNetId` — encodes `NetId?` without a boolean presence byte by mapping `null` $\leftrightarrow$ `0L`.

```kotlin
import com.awakekt.awake.net.*
import kotlinx.serialization.Serializable

@Serializable
sealed interface ClientMessage {
    @Serializable
    data class UseSkill(
        @PacketMaxBytes(64, nonEmpty = true) val skill: String,
        @PacketZeroNullNetId val target: NetId? = null,
    ) : ClientMessage

    @Serializable
    data class NaviPoint(
        @PacketMillis val x: Float,
        @PacketMillis val z: Float,
        @PacketZeroNullNetId val to: NetId? = null,
    ) : ClientMessage
}
```

---

## 3. Register opcodes in `PacketOpcodeRegistry`

Register each standard packet in one line and fall back to custom bit-packing only for hot-path delta packets:

```kotlin
private val clientRegistry = PacketOpcodeRegistry<ClientMessage>().apply {
    register<ClientMessage.UseSkill>(opcode = 9)
    register<ClientMessage.NaviPoint>(opcode = 115)
}

fun encodeClient(writer: PacketWriter, message: ClientMessage) {
    if (clientRegistry.encode(writer, message)) return
    when (message) {
        is ClientMessage.Input -> encodeBitPackedInput(writer, message)
        else -> error("Unregistered packet: ${message::class}")
    }
}

fun decodeClient(reader: PacketReader): ClientMessage? {
    val opcode = reader.readVarInt()
    val message = clientRegistry.decode(opcode, reader) ?: when (opcode) {
        INPUT_OPCODE -> decodeBitPackedInput(reader)
        else -> return null
    }
    return message.takeIf { reader.ok && reader.remaining == 0 }
}
```

- Always check `reader.ok && reader.remaining == 0` after decoding a frame so trailing garbage bytes are rejected.
- Never use `kotlinx.io.Buffer` / `ByteReadPacket` exceptions for untrusted packet validation; `PacketReader` uses a branchless `ok` flag to prevent exception stack-trace CPU DoS.

---

## 4. Structure authoritative servers with `GameServerHost` and `GameFeature`

Do not put WebSocket loops, tick loops, authentication, and gameplay handlers into a single monolithic `GameServer` class:

1. **Install `GameTransport` and `GameServerHost`** (`:awake:net:server-ktor`) inside an extracted `Application.configureServerModule(...)` function so tests run through Ktor `testApplication` without binding TCP ports.
2. **Decompose gameplay by domain into `GameFeature<C, S>` implementations** (`ChatFeature`, `PartyFeature`, `GuildFeature`, `CombatFeature`, `TradeFeature`), each registering its own message handlers on `MessageRouter`:
   ```kotlin
   class GuildFeature : GameFeature<ClientMessage, ServerMessage> {
       override fun install(host: GameServerHost<ClientMessage, ServerMessage>) {
           host.router.on<ClientMessage.GuildCreate> { session, msg -> ... }
           host.router.on<ClientMessage.GuildInvite> { session, msg -> ... }
       }
   }
   ```
3. **Keep the trust boundary server-authoritative**:
   - Assume the client binary and protocol are fully reverse-engineered (e.g., via AI-assisted Ghidra/JADX tools). Client obfuscation is never a substitute for a server check.
   - Clients send intentions/inputs, never authoritative coordinates, HP, cooldowns, or currency.
   - Enforce `NetOwner` on every entity-targeted input, clamp input tick windows, replicate only entities inside the client's spatial interest partition, and report anomalies to `ViolationSink` (`CountingViolationSink`) rather than logging per bad packet.
