"""Assembler and reference execution model for the supplied 2025 P4 record."""
from dataclasses import dataclass, field

MASK = 0xffffffff
INSTRUCTIONS = {
    'SPE': {'op': 0, 'funct': 0x29, 'format': '000000 rs rt rd 00000 101001', 'alias': 'BRC'},
    'CABC': {'op': 0x3c, 'format': '111100 rs rt offset16'},
    'LHBOC': {'op': 0x2d, 'format': '101101 base rt offset16'},
}


def signed(value, width=32):
    value &= (1 << width)-1
    return value-(1 << width) if value & (1 << (width-1)) else value


def spe(a, b):
    start = a & 31
    if start >= 25:
        return b
    window = (b >> start) & 255
    if window.bit_count() % 2:
        return b
    return int(f'{b:032b}'[::-1], 2)


def cabc(a, b):
    aa = a.to_bytes(4, 'little')
    bb = b.to_bytes(4, 'little')
    first = int.from_bytes(bytes([aa[2], bb[0], aa[3], bb[1]]), 'big')
    second = int.from_bytes(bytes([bb[0], aa[2], bb[3], aa[1]]), 'big')
    value = first ^ second
    zero_high = 16-((value >> 16) & 65535).bit_count()
    zero_low = 16-(value & 65535).bit_count()
    return value, zero_high == zero_low


def lhboc(word):
    lo, hi = word & 65535, word >> 16
    half = lo if lo.bit_count() >= hi.bit_count() else hi
    return signed(half, 16) & MASK


@dataclass
class Program:
    ops: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)

    def emit(self, name, *args):
        self.ops.append(('SPE' if name.upper() == 'BRC' else name.upper(), args))

    def label(self, name):
        assert name not in self.labels
        self.labels[name] = len(self.ops)

    def li(self, reg, value):
        value &= MASK
        if value >> 16:
            self.emit('LUI', reg, value >> 16)
            self.emit('ORI', reg, reg, value & 65535)
        else:
            self.emit('ORI', reg, 0, value)

    def word(self, address, value):
        assert address % 4 == 0 and 0 <= address <= 0x2ffc
        self.li(26, value)
        self.emit('SW', 26, 0, address)

    def finish(self):
        self.label('__halt')
        self.emit('BEQ', 0, 0, '__halt')

    def encoded(self):
        words, listing = [], []
        for index, (name, args) in enumerate(self.ops):
            args = list(args)
            if name in ('BEQ', 'CABC') and isinstance(args[-1], str):
                args[-1] = self.labels[args[-1]]-index-1
            if name in ('ADD', 'SUB', 'SPE'):
                rd, rs, rt = args
                funct = {'ADD': 0x20, 'SUB': 0x22, 'SPE': 0x29}[name]
                word = (rs << 21) | (rt << 16) | (rd << 11) | funct
                assembly = f'{name.lower()} ${rd}, ${rs}, ${rt}'
            elif name == 'LUI':
                rt, imm = args
                word = (0xf << 26) | (rt << 16) | imm
                assembly = f'lui ${rt}, 0x{imm:04x}'
            elif name == 'ORI':
                rt, rs, imm = args
                word = (0xd << 26) | (rs << 21) | (rt << 16) | imm
                assembly = f'ori ${rt}, ${rs}, 0x{imm:04x}'
            elif name in ('SW', 'LW', 'LHBOC'):
                rt, rs, imm = args
                assert -32768 <= imm <= 32767
                opcode = {'SW': 0x2b, 'LW': 0x23, 'LHBOC': 0x2d}[name]
                word = (opcode << 26) | (rs << 21) | (rt << 16) | (imm & 65535)
                assembly = f'{name.lower()} ${rt}, {imm}(${rs})'
            elif name in ('BEQ', 'CABC'):
                rs, rt, imm = args
                assert -32768 <= imm <= 32767
                opcode = 4 if name == 'BEQ' else 0x3c
                word = (opcode << 26) | (rs << 21) | (rt << 16) | (imm & 65535)
                assembly = f'{name.lower()} ${rs}, ${rt}, {imm}'
            else:
                raise ValueError(name)
            assert 0 <= word <= MASK
            words.append(word)
            listing.append(f'{0x3000+index*4:08x}  {word:08x}  {assembly}')
        assert len(words) <= 4096
        return words, listing


def execute(words, halt_index, limit=20000):
    regs, memory, events = [0]*32, [0]*3072, []
    pc = 0x3000
    counts = dict.fromkeys(INSTRUCTIONS, 0)
    for cycle in range(1, limit+1):
        assert pc % 4 == 0 and 0x3000 <= pc < 0x3000+4*len(words), hex(pc)
        instruction = words[(pc-0x3000)//4]
        op, rs, rt = instruction >> 26, (instruction >> 21) & 31, (instruction >> 16) & 31
        rd, funct, imm = (instruction >> 11) & 31, instruction & 63, instruction & 65535
        a, b = regs[rs], regs[rt]
        npc, write, store = (pc+4) & MASK, None, None
        if op == 0:
            if funct == 0x20:
                write = rd, (a+b) & MASK
            elif funct == 0x22:
                write = rd, (a-b) & MASK
            elif funct == 0x29:
                assert (instruction >> 6) & 31 == 0
                write = rd, spe(a, b)
                counts['SPE'] += 1
            elif instruction != 0:
                raise ValueError(f'Unknown R instruction {instruction:08x}')
        elif op == 0xf:
            write = rt, imm << 16
        elif op == 0xd:
            write = rt, a | imm
        elif op == 4:
            if a == b:
                npc = (npc+4*signed(imm, 16)) & MASK
        elif op in (0x23, 0x2b, 0x2d):
            ea = (a+signed(imm, 16)) & MASK
            assert ea <= 0x2fff, hex(ea)
            if op in (0x23, 0x2b):
                assert ea % 4 == 0
            if op == 0x2b:
                store = ea, b
            elif op == 0x23:
                write = rt, memory[ea//4]
            else:
                write = rt, lhboc(memory[ea//4])
                counts['LHBOC'] += 1
        elif op == 0x3c:
            value, taken = cabc(a, b)
            if taken:
                npc = (npc+4*signed(imm, 16)) & MASK
            else:
                write = rt, value
            counts['CABC'] += 1
        else:
            raise ValueError(f'Unknown instruction {instruction:08x}')
        if write and write[0] != 0:
            reg, value = write
            value &= MASK
            regs[reg] = value
            events.append({'cycle': cycle, 'pc': pc, 'kind': '$', 'target': reg, 'value': value})
        if store:
            address, value = store
            memory[address//4] = value
            events.append({'cycle': cycle, 'pc': pc, 'kind': '*', 'target': address, 'value': value})
        regs[0] = 0
        if pc == 0x3000+4*halt_index:
            assert npc == pc
            return events, regs, memory, pc, cycle, counts
        pc = npc
    raise RuntimeError('Reference program did not halt')


def format_event(event):
    target = str(event['target']) if event['kind'] == '$' else f"{event['target']:08x}"
    return f"@{event['pc']:08x}: {event['kind']}{target} <= {event['value']:08x}"
