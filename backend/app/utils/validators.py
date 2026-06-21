def allowed_file(filename: str) -> bool:
    """Only CSV files are accepted."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() == "csv"
    )