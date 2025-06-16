
def format_large_number(value):
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.3f} T"
    elif value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.3f} B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.3f} M"
    else:
        return f"{value:,.3f}"