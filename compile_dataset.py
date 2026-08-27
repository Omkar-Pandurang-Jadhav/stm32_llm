import json
import subprocess
import tempfile
from pathlib import Path
from collections import Counter
import time


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATASET = (
    BASE_DIR /
    "stm32_instruction_code_v3_code_only.jsonl"
)

RESULT_DIR = (
    BASE_DIR /
    "compile_results"
)

RESULT_DIR.mkdir(
    exist_ok=True
)


# ============================================================
# TOOLCHAIN
# ============================================================

ARM_GCC = (
    "/Applications/"
    "ArmGNUToolchain/"
    "15.3.rel1/"
    "arm-none-eabi/"
    "bin/"
    "arm-none-eabi-gcc"
)


# ============================================================
# STM32 CMSIS
# ============================================================

CMSIS_CORE = (
    "/Users/omkar/Documents/"
    "STM32CubeF1/"
    "Drivers/CMSIS/Include"
)

CMSIS_DEVICE = (
    "/Users/omkar/Documents/"
    "STM32CubeF1/"
    "Drivers/CMSIS/Device/ST/"
    "STM32F1xx/Include"
)


# ============================================================
# COMPILER FLAGS
# ============================================================

COMPILE_FLAGS = [
    ARM_GCC,

    "-mcpu=cortex-m3",
    "-mthumb",
    "-mfloat-abi=soft",

    "-DSTM32F103xB",

    f"-I{CMSIS_CORE}",
    f"-I{CMSIS_DEVICE}",

    "-c",
]


# ============================================================
# CHECK TOOLCHAIN
# ============================================================

def check_toolchain():

    if not Path(ARM_GCC).exists():

        raise FileNotFoundError(
            f"ARM GCC not found:\n{ARM_GCC}"
        )

    result = subprocess.run(
        [
            ARM_GCC,
            "--version"
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Could not execute ARM GCC:\n"
            + result.stderr
        )

    print(
        result.stdout.splitlines()[0]
    )


# ============================================================
# COMPILE ONE EXAMPLE
# ============================================================

def compile_code(code):

    with tempfile.TemporaryDirectory(
        prefix="stm32_compile_"
    ) as temp_dir:

        temp_dir = Path(
            temp_dir
        )

        source_file = (
            temp_dir /
            "main.c"
        )

        object_file = (
            temp_dir /
            "main.o"
        )

        source_file.write_text(
            code,
            encoding="utf-8"
        )

        command = (
            COMPILE_FLAGS
            + [
                str(source_file),
                "-o",
                str(object_file)
            ]
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        return (
            result.returncode == 0,
            result.stdout,
            result.stderr
        )


# ============================================================
# ERROR CLASSIFICATION
# ============================================================

def classify_error(stderr):

    text = stderr.lower()

    if "no such file or directory" in text:
        return "header_or_file"

    if "fatal error" in text:
        return "fatal_error"

    if "undeclared" in text:
        return "undeclared_identifier"

    if "not declared" in text:
        return "undeclared_identifier"

    if "no member named" in text:
        return "invalid_register"

    if "has no member" in text:
        return "invalid_register"

    if "expected" in text:
        return "syntax"

    if "invalid operands" in text:
        return "type_or_operator"

    if "incompatible" in text:
        return "type_error"

    if "implicit declaration" in text:
        return "missing_function"

    if "warning:" in text and "error:" not in text:
        return "warning_only"

    return "other"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("STM32F103VB DATASET COMPILATION")
    print("=" * 70)

    print()

    # --------------------------------------------------------
    # CHECK DATASET
    # --------------------------------------------------------

    if not DATASET.exists():

        raise FileNotFoundError(
            f"Dataset not found:\n{DATASET}"
        )

    # --------------------------------------------------------
    # CHECK TOOLCHAIN
    # --------------------------------------------------------

    check_toolchain()

    print()

    print(
        "Dataset:",
        DATASET
    )

    print(
        "Compiler:",
        ARM_GCC
    )

    print()

    # --------------------------------------------------------
    # OUTPUT FILES
    # --------------------------------------------------------

    all_results_file = (
        RESULT_DIR /
        "compilation_results.jsonl"
    )

    passed_file = (
        RESULT_DIR /
        "passed.jsonl"
    )

    failed_file = (
        RESULT_DIR /
        "failed.jsonl"
    )

    summary_file = (
        RESULT_DIR /
        "summary.json"
    )

    # --------------------------------------------------------
    # COUNTERS
    # --------------------------------------------------------

    total = 0
    passed = 0
    failed = 0

    error_categories = Counter()

    start_time = time.time()

    # --------------------------------------------------------
    # OPEN DATASET
    # --------------------------------------------------------

    with open(
        DATASET,
        "r",
        encoding="utf-8"
    ) as dataset_file, \
    open(
        all_results_file,
        "w",
        encoding="utf-8"
    ) as all_file, \
    open(
        passed_file,
        "w",
        encoding="utf-8"
    ) as pass_file, \
    open(
        failed_file,
        "w",
        encoding="utf-8"
    ) as fail_file:

        for line_number, line in enumerate(
            dataset_file,
            start=1
        ):

            line = line.strip()

            if not line:
                continue

            total += 1

            # ------------------------------------------------
            # PARSE JSON
            # ------------------------------------------------

            try:

                record = json.loads(
                    line
                )

            except json.JSONDecodeError as exc:

                failed += 1

                result = {
                    "line": line_number,
                    "id": None,
                    "prompt": None,
                    "status": "FAIL",
                    "error_type": "invalid_json",
                    "compiler_error": str(exc)
                }

                all_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

                fail_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

                continue

            example_id = record.get(
                "id"
            )

            prompt = record.get(
                "prompt",
                ""
            )

            code = record.get(
                "response",
                ""
            )

            # ------------------------------------------------
            # CHECK CODE FIELD
            # ------------------------------------------------

            if not isinstance(
                code,
                str
            ) or not code.strip():

                failed += 1

                result = {
                    "line": line_number,
                    "id": example_id,
                    "prompt": prompt,
                    "status": "FAIL",
                    "error_type": "empty_code",
                    "compiler_error": "Empty response field"
                }

                all_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

                fail_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

                continue

            # ------------------------------------------------
            # COMPILE
            # ------------------------------------------------

            success, stdout, stderr = (
                compile_code(
                    code
                )
            )

            if success:

                passed += 1

                result = {
                    "line": line_number,
                    "id": example_id,
                    "prompt": prompt,
                    "status": "PASS",
                    "compiler_error": ""
                }

                all_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

                pass_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

            else:

                failed += 1

                error_type = (
                    classify_error(
                        stderr
                    )
                )

                error_categories[
                    error_type
                ] += 1

                result = {
                    "line": line_number,
                    "id": example_id,
                    "prompt": prompt,
                    "status": "FAIL",
                    "error_type": error_type,
                    "compiler_error": stderr
                }

                all_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

                fail_file.write(
                    json.dumps(
                        result,
                        ensure_ascii=False
                    )
                    + "\n"
                )

            # ------------------------------------------------
            # PROGRESS
            # ------------------------------------------------

            if total % 100 == 0:

                elapsed = (
                    time.time()
                    - start_time
                )

                rate = (
                    total / elapsed
                    if elapsed > 0
                    else 0
                )

                print(
                    f"[{total:5d}] "
                    f"PASS={passed:5d} "
                    f"FAIL={failed:5d} "
                    f"Rate={rate:.1f}/sec"
                )

    # ========================================================
    # FINAL STATISTICS
    # ========================================================

    elapsed = (
        time.time()
        - start_time
    )

    success_rate = (
        passed / total * 100
        if total
        else 0
    )

    failure_rate = (
        failed / total * 100
        if total
        else 0
    )

    summary = {
        "dataset": str(
            DATASET
        ),
        "compiler": ARM_GCC,
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate_percent": round(
            success_rate,
            2
        ),
        "failure_rate_percent": round(
            failure_rate,
            2
        ),
        "elapsed_seconds": round(
            elapsed,
            2
        ),
        "error_categories": dict(
            error_categories
        )
    }

    with open(
        summary_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2
        )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 70)
    print("FINAL COMPILATION REPORT")
    print("=" * 70)

    print(
        f"Total examples       : {total}"
    )

    print(
        f"Successful           : {passed}"
    )

    print(
        f"Failed               : {failed}"
    )

    print(
        f"Success rate         : {success_rate:.2f}%"
    )

    print(
        f"Failure rate         : {failure_rate:.2f}%"
    )

    print(
        f"Time                 : {elapsed:.2f} sec"
    )

    print()

    print(
        "ERROR CATEGORIES"
    )

    print(
        "-" * 70
    )

    if error_categories:

        for category, count in (
            error_categories.most_common()
        ):

            print(
                f"{category:30s}: {count}"
            )

    else:

        print(
            "No compilation errors."
        )

    print()

    print(
        "Results:"
    )

    print(
        all_results_file
    )

    print(
        passed_file
    )

    print(
        failed_file
    )

    print(
        summary_file
    )

    print("=" * 70)


if __name__ == "__main__":
    main()