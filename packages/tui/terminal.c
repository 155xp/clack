#define _XOPEN_SOURCE 700
#include <errno.h>
#include <inttypes.h>
#include <locale.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>
#include <wchar.h>

enum { MAX_ITEMS = 128, TEXT_CAP = 256 };
typedef enum { PANEL, LABEL, ROW, METRIC, PROGRESS, OPTION } Kind;
typedef struct {
    Kind kind;
    char name[TEXT_CAP], value[TEXT_CAP];
    int64_t number, total;
} Item;

static Item items[MAX_ITEMS];
static size_t item_count;
static char title[TEXT_CAP];
static bool interactive, ascii, color, registered;
static struct termios original_terminal;
static const int handled_signals[] = {SIGINT, SIGTERM, SIGHUP};
static struct sigaction original_signals[3];
static size_t installed_signals;
static volatile sig_atomic_t interrupted;

static void on_signal(int number) {
    interrupted = number;
}

/* Keep complete UTF-8 characters and replace terminal control characters. */
static void copy_text(char destination[TEXT_CAP], const char *source) {
    size_t used = 0;
    mbstate_t state = {0};
    if (!source) source = "";
    while (*source && used < TEXT_CAP - 1) {
        wchar_t character;
        size_t length = mbrtowc(&character, source, MB_CUR_MAX, &state);
        if (length == (size_t)-1 || length == (size_t)-2) {
            state = (mbstate_t){0};
            destination[used++] = '?';
            source++;
        } else {
            if (used + length >= TEXT_CAP) break;
            if (character < 32 || (character >= 127 && character <= 159)) {
                destination[used++] = ' ';
            } else {
                memcpy(destination + used, source, length);
                used += length;
            }
            source += length;
        }
    }
    destination[used] = '\0';
}

static int text_columns(const char *text, int limit, bool output) {
    int columns = 0;
    mbstate_t state = {0};
    while (*text) {
        wchar_t character;
        size_t length = mbrtowc(&character, text, MB_CUR_MAX, &state);
        if (length == (size_t)-1 || length == (size_t)-2 || !length) break;
        int width = wcwidth(character);
        if (width < 0) width = 1;
        if (columns + width > limit) break;
        if (output) fwrite(text, 1, length, stdout);
        columns += width;
        text += length;
    }
    return columns;
}

void clack_tui_end(void) {
    if (!interactive) return;
    fputs("\033[0m\033[?25h\033[?1049l", stdout);
    fflush(stdout);
    (void)tcsetattr(STDIN_FILENO, TCSANOW, &original_terminal);
    interactive = false;
    while (installed_signals) {
        installed_signals--;
        (void)sigaction(handled_signals[installed_signals], &original_signals[installed_signals], NULL);
    }
}

void clack_tui_begin(const char *name) {
    clack_tui_end();
    (void)setlocale(LC_CTYPE, "");
    copy_text(title, name);
    item_count = 0;
    interrupted = 0;
    const char *ascii_setting = getenv("CLACK_TUI_ASCII");
    ascii = (ascii_setting && *ascii_setting) || MB_CUR_MAX == 1;
    color = getenv("NO_COLOR") == NULL;
    if (!registered) {
        atexit(clack_tui_end);
        registered = true;
    }
}

static Item *append(Kind kind, const char *name, const char *value) {
    if (item_count == MAX_ITEMS) return NULL;
    Item *item = &items[item_count++];
    *item = (Item){.kind = kind};
    copy_text(item->name, name);
    copy_text(item->value, value);
    return item;
}

void clack_tui_panel(const char *name) { (void)append(PANEL, name, ""); }
void clack_tui_label(const char *value) { (void)append(LABEL, value, ""); }
void clack_tui_row(const char *name, const char *value) { (void)append(ROW, name, value); }

void clack_tui_metric(const char *name, int64_t value) {
    Item *item = append(METRIC, name, "");
    if (item) snprintf(item->value, sizeof(item->value), "%" PRId64, value);
}

void clack_tui_progress(const char *name, int64_t value, int64_t total) {
    Item *item = append(PROGRESS, name, "");
    if (item) {
        item->number = value;
        item->total = total;
    }
}

void clack_tui_option(int64_t id, const char *name) {
    if (id <= 0) return;
    Item *item = append(OPTION, name, "");
    if (item) item->number = id;
}

static void terminal_size(int *width, int *height) {
    struct winsize size = {0};
    (void)ioctl(STDOUT_FILENO, TIOCGWINSZ, &size);
    *width = size.ws_col ? size.ws_col : 80;
    *height = size.ws_row ? size.ws_row : 24;
    if (*width > 100) *width = 100;
    if (*width < 8) *width = 8;
    if (*height < 8) *height = 8;
}

static void border(int width, const char *left, const char *right) {
    fputs(ascii ? "+" : left, stdout);
    for (int column = 0; column < width - 2; column++) fputs(ascii ? "-" : "─", stdout);
    fputs(ascii ? "+\n" : right, stdout);
    if (!ascii) putchar('\n');
}

static void line(const char *name, const char *value, int width, bool strong, bool selected) {
    int inner = width - 4;
    int right = text_columns(value, inner / 2, false);
    if (interactive && color && selected) fputs("\033[7m", stdout);
    else if (interactive && color && strong) fputs("\033[1;32m", stdout);
    fputs(ascii ? "| " : "│ ", stdout);
    int used = text_columns(name, inner - right - (right ? 1 : 0), true);
    for (int column = used; column < inner - right; column++) putchar(' ');
    (void)text_columns(value, right, true);
    fputs(ascii ? " |" : " │", stdout);
    if (interactive && color) fputs("\033[0m", stdout);
    putchar('\n');
}

static void progress_text(const Item *item, char *buffer, size_t capacity, int width) {
    long double ratio = item->total > 0 ? (long double)item->number / (long double)item->total : 0;
    if (ratio < 0) ratio = 0;
    if (ratio > 1) ratio = 1;
    int cells = width > 60 ? 20 : 10;
    int filled = (int)(ratio * cells);
    char bar[21];
    for (int i = 0; i < cells; i++) bar[i] = i < filled ? '#' : '-';
    bar[cells] = '\0';
    snprintf(buffer, capacity, "[%s] %d%%", bar, (int)(ratio * 100));
}

static void render(int selected_item, int width, int height) {
    if (interactive) fputs("\033[H\033[2J", stdout);
    border(width, "┌", "┐");
    line(title, "clack", width, true, false);
    border(width, "├", "┤");
    size_t start = 0;
    size_t available = interactive ? (size_t)(height - 7) : item_count;
    if (selected_item >= (int)available) start = (size_t)selected_item - available + 1;
    for (size_t i = start; i < item_count && i < start + available; i++) {
        const Item *item = &items[i];
        char value[TEXT_CAP], name[TEXT_CAP], marked[TEXT_CAP + 4];
        copy_text(value, item->value);
        copy_text(name, item->name);
        if (item->kind == PROGRESS) progress_text(item, value, sizeof(value), width);
        if (item->kind == OPTION) {
            const char *marker = (int)i == selected_item ? (ascii ? "> " : "› ") : "  ";
            snprintf(marked, sizeof(marked), "%s%s", marker, item->name);
            copy_text(name, marked);
        }
        line(name, value, width, item->kind == PANEL, (int)i == selected_item);
    }
    border(width, "├", "┤");
    line(ascii ? "j/k move  enter choose  q quit" : "↑↓ move  enter choose  q quit", "", width, false, false);
    border(width, "└", "┘");
    fflush(stdout);
}

static bool enter_terminal(void) {
    const char *term = getenv("TERM");
    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) || (term && !strcmp(term, "dumb"))) return false;
    if (tcgetattr(STDIN_FILENO, &original_terminal) != 0) return false;
    struct termios raw = original_terminal;
    raw.c_lflag &= (tcflag_t)~(ICANON | ECHO | IEXTEN);
    raw.c_iflag &= (tcflag_t)~(IXON | ICRNL);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 1;
    if (tcsetattr(STDIN_FILENO, TCSANOW, &raw) != 0) return false;
    interactive = true;
    struct sigaction action = {0};
    action.sa_handler = on_signal;
    sigemptyset(&action.sa_mask);
    for (size_t i = 0; i < sizeof(handled_signals) / sizeof(handled_signals[0]); i++) {
        if (sigaction(handled_signals[i], &action, &original_signals[i]) != 0) break;
        installed_signals++;
    }
    fputs("\033[?1049h\033[?25l", stdout);
    return true;
}

static int key(void) {
    unsigned char value;
    if (read(STDIN_FILENO, &value, 1) != 1) return -1;
    if (value != 27) return value;
    unsigned char prefix, arrow;
    if (read(STDIN_FILENO, &prefix, 1) != 1) return 27;
    if (prefix != '[' || read(STDIN_FILENO, &arrow, 1) != 1) return 27;
    return arrow == 'A' ? 'k' : arrow == 'B' ? 'j' : -1;
}

int64_t clack_tui_run(void) {
    size_t options[MAX_ITEMS], option_count = 0, selected = 0;
    for (size_t i = 0; i < item_count; i++) {
        if (items[i].kind == OPTION) options[option_count++] = i;
    }
    int width, height;
    terminal_size(&width, &height);
    if (!enter_terminal()) {
        ascii = true;
        render(-1, width, height);
        return 0;
    }
    int64_t result = 0;
    bool redraw = true;
    while (!interrupted) {
        int next_width, next_height;
        terminal_size(&next_width, &next_height);
        redraw = redraw || next_width != width || next_height != height;
        width = next_width;
        height = next_height;
        if (redraw) render(option_count ? (int)options[selected] : -1, width, height);
        int pressed = key();
        redraw = pressed != -1;
        if (pressed == 'q' || pressed == 27) break;
        if (pressed == '\r' || pressed == '\n') {
            if (option_count) result = items[options[selected]].number;
            break;
        }
        if (option_count && pressed == 'j') selected = (selected + 1) % option_count;
        if (option_count && pressed == 'k') selected = (selected + option_count - 1) % option_count;
    }
    clack_tui_end();
    return result;
}

int64_t clack_tui_menu3(const char *name, const char *first, const char *second, const char *third) {
    clack_tui_begin(name);
    clack_tui_option(1, first);
    clack_tui_option(2, second);
    clack_tui_option(3, third);
    return clack_tui_run();
}
