"""Distinct native kernels with matching C programs and independent oracles."""

from math import gcd, isqrt


_HEADER = '#include <stdint.h>\n#include <stdio.h>\n#include <inttypes.h>\n'

_GCD = '''fn gcd(a: int, b: int) -> int:
    requires 0 <= a <= 1000000 and 0 < b <= 1000000
    ensures 0 <= result <= 1000000
    x = a
    y = b
    while y != 0:
        invariant 0 <= x <= 1000000 and 0 <= y <= 1000000
        decreases y
        remainder = x % y
        x = y
        y = remainder
    return x

fn workload(rounds: int) -> int:
    requires 0 <= rounds <= 10000000
    ensures 0 <= result <= rounds * 1000000
    i = 0
    seed = 1
    total = 0
    while i < rounds:
        invariant 0 <= i <= rounds and 0 <= seed < 1000000
        invariant 0 <= total <= i * 1000000
        decreases rounds - i
        seed = (seed * 17 + 23) % 1000000
        total = total + gcd(seed + 1, 123456)
        i = i + 1
    return total

fn main():
    print(workload(ROUNDS))
'''

_GCD_C = _HEADER + '''static int64_t gcd_kernel(int64_t a, int64_t b) {
    int64_t x=a, y=b;
    while (y != 0) { int64_t remainder=x%y; x=y; y=remainder; }
    return x;
}
static int64_t workload(int64_t rounds) {
    int64_t seed=1, total=0;
    for (int64_t i=0;i<rounds;i++) {
        seed=(seed*17+23)%1000000;
        total+=gcd_kernel(seed+1,123456);
    }
    return total;
}
int main(void) { printf("%" PRId64 "\\n",workload(INT64_C(ROUNDS))); return 0; }
'''

_SQRT = '''fn square_root(n: int) -> int:
    requires 0 <= n <= 1000000006
    ensures 0 <= result < 31624
    low = 0
    high = 31624
    while low + 1 < high:
        invariant 0 <= low < high <= 31624
        decreases high - low
        middle = (low + high) / 2
        if middle * middle <= n:
            low = middle
        else:
            high = middle
    return low

fn workload(rounds: int) -> int:
    requires 0 <= rounds <= 10000000
    ensures 0 <= result <= rounds * 31624
    i = 0
    seed = 1
    total = 0
    while i < rounds:
        invariant 0 <= i <= rounds and 0 <= seed <= 1000000006
        invariant 0 <= total <= i * 31624
        decreases rounds - i
        seed = (seed * 48271) % 1000000007
        total = total + square_root(seed)
        i = i + 1
    return total

fn main():
    print(workload(ROUNDS))
'''

_SQRT_C = _HEADER + '''static int64_t square_root(int64_t n) {
    int64_t low=0,high=31624;
    while (low+1<high) {
        int64_t middle=(low+high)/2;
        if (middle*middle<=n) low=middle; else high=middle;
    }
    return low;
}
static int64_t workload(int64_t rounds) {
    int64_t seed=1,total=0;
    for (int64_t i=0;i<rounds;i++) {
        seed=(seed*48271)%1000000007;
        total+=square_root(seed);
    }
    return total;
}
int main(void) { printf("%" PRId64 "\\n",workload(INT64_C(ROUNDS))); return 0; }
'''


def _array_sources(rounds):
    invariant = '\n'.join(f'        invariant 0 <= values[{i}] < 1000000' for i in range(8))
    updates = '\n'.join(f'        values[{i}] = (values[{i}] * 17 + 23) % 1000000' for i in range(8))
    additions = ' + '.join(f'values[{i}]' for i in range(8))
    source = f'''fn workload(rounds: int) -> int:
    requires 0 <= rounds <= 100000000
    ensures 0 <= result < 8000000
    values = [1, 2, 3, 4, 5, 6, 7, 8]
    i = 0
    while i < rounds:
        invariant 0 <= i <= rounds
{invariant}
        decreases rounds - i
{updates}
        i = i + 1
    return {additions}

fn main():
    print(workload({rounds}))
'''
    c_updates = '\n'.join(f'        values[{i}]=(values[{i}]*17+23)%1000000;' for i in range(8))
    c_source = _HEADER + f'''static int64_t workload(int64_t rounds) {{
    int64_t values[8]={{1,2,3,4,5,6,7,8}};
    for (int64_t i=0;i<rounds;i++) {{
{c_updates}
    }}
    return {additions};
}}
int main(void) {{ printf("%" PRId64 "\\n",workload(INT64_C({rounds}))); return 0; }}
'''
    return source, c_source


def _reference(rounds, operation):
    seed, total = 1, 0
    for _ in range(rounds):
        if operation == 'gcd':
            seed = (seed * 17 + 23) % 1000000
            total += gcd(seed + 1, 123456)
        else:
            seed = (seed * 48271) % 1000000007
            total += isqrt(seed)
    return str(total) + '\n'


def _array_reference(rounds):
    # Independent logarithmic matrix exponentiation of the affine transition,
    # rather than running the native program's eight recurrence loops.
    def multiply(a, b):
        return tuple(sum(a[i*2+k]*b[k*2+j] for k in range(2)) % 1000000 for i in range(2) for j in range(2))
    result, power = (1, 0, 0, 1), (17, 23, 0, 1)
    while rounds:
        if rounds & 1:
            result = multiply(result, power)
        power = multiply(power, power)
        rounds //= 2
    return str(sum((result[0]*seed+result[1]) % 1000000 for seed in range(1, 9))) + '\n'


def cases(scale=1):
    gcd_rounds, sqrt_rounds, array_rounds = 300000*scale, 300000*scale, 2000003*scale
    array, array_c = _array_sources(array_rounds)
    return [
        {'name':'gcd','label':'Variable-input Euclidean GCD','clack':_GCD.replace('ROUNDS',str(gcd_rounds)),
         'c':_GCD_C.replace('ROUNDS',str(gcd_rounds)),'expected':_reference(gcd_rounds,'gcd'),'work_units':gcd_rounds},
        {'name':'sqrt','label':'Branch-heavy integer square root','clack':_SQRT.replace('ROUNDS',str(sqrt_rounds)),
         'c':_SQRT_C.replace('ROUNDS',str(sqrt_rounds)),'expected':_reference(sqrt_rounds,'sqrt'),'work_units':sqrt_rounds},
        {'name':'array','label':'Eight-state fixed-array updates','clack':array,'c':array_c,
         'expected':_array_reference(array_rounds),'work_units':array_rounds*8},
    ]
