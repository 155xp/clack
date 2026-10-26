# 7. Build an inventory report

[Previous: Fixing errors](06-fixing-errors.md) · [Tutorial index](README.md) · [Next: Libraries](08-libraries.md)

This project combines records, arrays, contracts, loops, and parallel calls. You will summarize stock at two warehouses and combine their totals. It uses fixed batches of four stock counts because the current language has fixed-size arrays.

## Choose the data and promises

Each warehouse supplies an `int[4]`. A count must be between zero and one million. Those bounds describe valid stock data and make every possible addition fit in a signed 64-bit integer.

`StockReport` gives names to the two answers: `total` units and the number of `empty` entries. Returning a record keeps those answers together. The caller can read its fields without remembering which array position means which measurement.

The contract makes three promises. The total equals the sum of the four inputs, the total stays within four million, and the number of empty entries is between zero and four. The count promise is deliberately weaker than “exactly the number of zero entries.” The implementation counts zeros, but a bound alone does not prove that full behavioral claim. Writing a useful contract requires choosing which facts callers need and recognizing what remains unstated.

## Write the program

Save this as `examples/tutorials/07-project.clack`, or run the included file:

<!-- clack:file=../../examples/tutorials/07-project.clack -->
```clack
type StockReport:
    total: int
    empty: int

fn analyze(stock: int[4]) -> StockReport:
    requires 0 <= stock[0] <= 1000000
    requires 0 <= stock[1] <= 1000000
    requires 0 <= stock[2] <= 1000000
    requires 0 <= stock[3] <= 1000000
    ensures result.total == stock[0] + stock[1] + stock[2] + stock[3]
    ensures 0 <= result.total <= 4000000
    ensures 0 <= result.empty <= len(stock)

    total = stock[0] + stock[1] + stock[2] + stock[3]
    i = 0
    empty = 0
    while i < len(stock):
        invariant 0 <= i <= len(stock)
        invariant 0 <= empty <= i
        decreases len(stock) - i
        if stock[i] == 0:
            empty = empty + 1
        i = i + 1
    return StockReport(total, empty)

fn main():
    north_stock = [12, 0, 8, 0]
    south_stock = [5, 7, 0, 3]
    parallel:
        north = analyze(north_stock)
        south = analyze(south_stock)
    print(north.total)
    print(north.empty)
    print(south.total)
    print(south.empty)
    print(north.total + south.total)
```

With the virtual environment active, run from the repository root:

```sh
clack run examples/tutorials/07-project.clack
```

The exact output is:

```text
20
2
15
1
35
```

The first two lines describe the north warehouse, the next two describe the south warehouse, and the last line is the combined stock total. Labels are explained here because string output is not supported yet.

## Follow the reasoning

The total uses a direct four-element sum. Each input is bounded, so every executable intermediate fits. Its exact postcondition lets the caller connect the returned total to the original data.

The loop visits indices zero through three. `0 <= i <= len(stock)` supplies the index and exit bounds. Together with the loop condition, it proves `stock[i]` exists. `0 <= empty <= i` says the count never exceeds the number of entries already visited. Increasing `empty` only in the zero branch preserves that bound after `i` advances. The remaining length decreases on each iteration, establishing termination.

Both warehouse calls are independent. Each receives a value and produces its own record. `parallel:` starts the work and waits for both records before printing begins. Output order follows the statements in main, regardless of which worker finishes first. These tiny batches demonstrate the semantics; thread overhead can outweigh any timing benefit.

## Exercises

1. Replace north's data with `[0, 0, 0, 0]`. Predict all five output lines before running it.
2. Add a third independent warehouse with `[1, 2, 3, 4]`. Print its total and include it in the combined total.
3. Change a count to `-1`. Which function promise prevents the call?

<details>
<summary>Answers</summary>

1. The output becomes `0`, `4`, `15`, `1`, and `15`, each on its own line.
2. Add a distinct binding such as `east = analyze([1, 2, 3, 4])` inside the existing parallel block. Its total is `10`; the combined total for the original two warehouses plus east is `45`. Each total is at most four million, so the three-way sum also fits.
3. The matching `requires 0 <= stock[index] <= 1000000` clause fails at the call. Correct the data or deliberately redesign the accepted input domain and its proofs.

</details>

You can now build a complete native program whose data, arithmetic, loops, and independent jobs have explicit semantics. Continue with the [language guide](../language.md) for lookup or the [verification model](../verification.md) for the proof rules behind these lessons.
