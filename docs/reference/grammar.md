# Grammar

This grammar describes Clack 0.1's source forms. Use it with the [lexical rules](lexical-syntax.md) and [statement semantics](functions-control-flow.md): a grammatical program can still fail type checking or verification. The [reference index](README.md) links the remaining rules.

Quoted strings are literal tokens. `A | B` chooses an alternative, `[ A ]` makes a form optional, and `{ A }` repeats it zero or more times. A comma between grammar items means sequence; it is not a source comma unless quoted.

## Lines and names

`NEWLINE` ends a logical statement. `INDENT` begins a deeper indentation level and `DEDENT` returns to an earlier level. A colon introducing a block must be followed by a logical newline and an indented, nonempty body. Statements cannot follow the colon on the same logical line. Use consistent spaces; indentation containing tabs is rejected.

Blank lines and `#` comments contribute no statements. Newlines inside parentheses or square brackets allow expressions and argument lists to span physical lines without introducing a block. Comments may contain Unicode text, but identifiers use only ASCII characters.

```ebnf
letter          = "A" … "Z" | "a" … "z" | "_" ;
digit           = "0" … "9" ;
nonzero_digit   = "1" … "9" ;
name            = letter, { letter | digit } ;
integer         = "0" | nonzero_digit, { digit } ;
```

The `name` productions below exclude syntax keywords. Some otherwise valid names, including `result`, `print`, and `len`, have additional binding restrictions. A minus sign is a unary operator, rather than part of the integer token. Hexadecimal, floating-point, and underscore-separated integer literals are unsupported.

## Declarations

```ebnf
source_file     = top_level, { top_level }, END ;
top_level       = import_statement | declaration ;
import_statement = "from", module_path, "import",
                   name, { ",", name }, [ "," ], NEWLINE ;
module_path     = name, { ".", name } ;
declaration     = record | function ;

record          = "type", name, ":", NEWLINE, INDENT,
                  field, { field }, DEDENT ;
field           = name, ":", type, NEWLINE ;

function        = "fn", name, "(", [ parameters ], ")",
                  [ "->", type ], ":", NEWLINE, INDENT,
                  { contract }, statement, { statement }, DEDENT ;
parameters      = parameter, { ",", parameter }, [ "," ] ;
parameter       = name, ":", type ;
type            = type_name, [ "[", integer, "]" ] ;
type_name       = "int" | "bool" | "unit" | name ;
contract        = ( "requires" | "ensures" ), expression, NEWLINE ;
```

Only `main` may omit the return annotation. Its valid signature has no parameters and returns `unit`, whether written explicitly or omitted. Every other function needs a result type and a value return on every syntactically continuing path. The root program must declare exactly one `main`; imported library files must not declare it. A library can contain only records or only imports, provided its source file is nonempty.

Imports are top-level forms and do not belong inside statement suites. They may be placed among other top-level declarations, although putting them first is the usual convention. Module paths have no leading dot. The import list may have a trailing comma but cannot use parentheses, `*`, aliases, or a renamed binding. A selected name denotes a function or record, including one reexported by that module. See the [library guide](../libraries.md) for file resolution and scope rules.

Semantic type checking limits array types to `int[N]` and `bool[N]`, with `1 <= N <= 1000000`; named record types are also supported. `unit` is restricted to main's result. The broader `type` production reflects what the parser reads before those checks. Records need distinct fields and finite, nonrecursive value layouts.

Contracts must precede the function's executable statements. They may be interleaved textually; each kind retains its own declaration order during verification. Preconditions are processed before postconditions. Main cannot declare preconditions.

## Statements

```ebnf
suite           = ":", NEWLINE, INDENT,
                  statement, { statement }, DEDENT ;
statement       = assignment | array_assignment | return_statement
                | assertion | expression_statement
                | if_statement | while_statement | parallel_statement ;
assignment      = name, "=", expression, NEWLINE ;
array_assignment = name, "[", expression, "]", "=", expression, NEWLINE ;
return_statement = "return", [ expression ], NEWLINE ;
assertion       = "assert", expression, NEWLINE ;
expression_statement = expression, NEWLINE ;

if_statement    = "if", expression, suite,
                  { "elif", expression, suite }, [ "else", suite ] ;
while_statement = "while", expression, ":", NEWLINE, INDENT,
                  invariant, { invariant }, decreases,
                  statement, { statement }, DEDENT ;
invariant       = "invariant", expression, NEWLINE ;
decreases       = "decreases", expression, NEWLINE ;

parallel_statement = "parallel", ":", NEWLINE, INDENT,
                     job, { job }, DEDENT ;
job             = name, "=", call, NEWLINE ;
```

Expression statements are parsed generally, then restricted to `print(value)` in main. Parallel jobs must call user functions: a constructor, builtin, or call to main is invalid. Result names must be distinct and cannot occur in any argument expression in that block. Assignment to a field, a parameter, or a nested index target is unsupported. A bare `return` belongs only to main.

Assignment targets and job calls are recognized from their parsed expression form. Redundant grouping parentheses do not change that form; the productions above show their unparenthesized spellings.

## Expressions

```ebnf
expression      = disjunction ;
disjunction     = conjunction, { "or", conjunction } ;
conjunction     = negation, { "and", negation } ;
negation        = "not", negation | comparison ;
comparison      = sum, { comparison_op, sum } ;
comparison_op   = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
sum             = product, { ( "+" | "-" ), product } ;
product         = unary, { ( "*" | "/" | "%" ), unary } ;
unary           = ( "+" | "-" ), unary | postfix ;
postfix         = primary, { ".", name | "[", expression, "]" } ;
primary         = integer | "true" | "false" | name | call
                | "(", expression, ")" | array_literal ;
call            = name, "(", [ arguments ], ")" ;
arguments       = expression, { ",", expression }, [ "," ] ;
array_literal   = "[", arguments, "]" ;
```

Thus `not a < b` means `not (a < b)`. Arithmetic operators at the same precedence associate left to right. A chain such as `a < b <= c` becomes pairwise comparisons joined by short-circuiting `and`. Calls require a simple name; calling an arbitrary expression is unsupported. Parameter, argument, and array lists allow a trailing comma. Array literals cannot be empty.

Proof expressions use this expression grammar but prohibit calls other than `len`. Types, defined operations, bounds, and the proof obligations still apply after parsing.
