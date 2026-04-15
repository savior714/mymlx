#!/usr/bin/env bash
# Test script for log level input validation

valid_log_levels=("DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL")

echo "=== Log Level Input Validation Tests ==="
echo ""

# Test 1: Empty input defaults to INFO
echo "Test 1: Empty input (Enter key)"
USER_LOG=""
input=""
while true; do
    if [[ -z "$input" ]]; then
        USER_LOG="INFO"
        break
    fi
    
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        idx=$((input - 1))
        if [[ $idx -ge 0 && $idx -lt ${#valid_log_levels[@]} ]]; then
            USER_LOG="${valid_log_levels[$idx]}"
            break
        fi
    fi
    
    input_upper=$(echo "$input" | tr '[:lower:]' '[:upper:]')
    for level in "${valid_log_levels[@]}"; do
        if [[ "$input_upper" == "$level" ]]; then
            USER_LOG="$input_upper"
            break 2
        fi
    done
    echo "Invalid log level. Please choose from: ${valid_log_levels[*]}"
done
echo "  Result: USER_LOG=$USER_LOG"
[[ "$USER_LOG" == "INFO" ]] && echo "  ✓ PASS" || echo "  ✗ FAIL"
echo ""

# Test 2: Numeric selection (1 = DEBUG)
echo "Test 2: Numeric input '1' (should select DEBUG)"
USER_LOG=""
input="1"
while true; do
    if [[ -z "$input" ]]; then
        USER_LOG="INFO"
        break
    fi
    
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        idx=$((input - 1))
        if [[ $idx -ge 0 && $idx -lt ${#valid_log_levels[@]} ]]; then
            USER_LOG="${valid_log_levels[$idx]}"
            break
        fi
    fi
    
    input_upper=$(echo "$input" | tr '[:lower:]' '[:upper:]')
    for level in "${valid_log_levels[@]}"; do
        if [[ "$input_upper" == "$level" ]]; then
            USER_LOG="$input_upper"
            break 2
        fi
    done
    echo "Invalid log level. Please choose from: ${valid_log_levels[*]}"
done
echo "  Result: USER_LOG=$USER_LOG"
[[ "$USER_LOG" == "DEBUG" ]] && echo "  ✓ PASS" || echo "  ✗ FAIL"
echo ""

# Test 3: String input (case-insensitive)
echo "Test 3: String input 'warning' (should select WARNING)"
USER_LOG=""
input="warning"
while true; do
    if [[ -z "$input" ]]; then
        USER_LOG="INFO"
        break
    fi
    
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        idx=$((input - 1))
        if [[ $idx -ge 0 && $idx -lt ${#valid_log_levels[@]} ]]; then
            USER_LOG="${valid_log_levels[$idx]}"
            break
        fi
    fi
    
    input_upper=$(echo "$input" | tr '[:lower:]' '[:upper:]')
    for level in "${valid_log_levels[@]}"; do
        if [[ "$input_upper" == "$level" ]]; then
            USER_LOG="$input_upper"
            break 2
        fi
    done
    echo "Invalid log level. Please choose from: ${valid_log_levels[*]}"
done
echo "  Result: USER_LOG=$USER_LOG"
[[ "$USER_LOG" == "WARNING" ]] && echo "  ✓ PASS" || echo "  ✗ FAIL"
echo ""

# Test 4: String input with uppercase
echo "Test 4: String input 'ERROR' (should select ERROR)"
USER_LOG=""
input="ERROR"
while true; do
    if [[ -z "$input" ]]; then
        USER_LOG="INFO"
        break
    fi
    
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        idx=$((input - 1))
        if [[ $idx -ge 0 && $idx -lt ${#valid_log_levels[@]} ]]; then
            USER_LOG="${valid_log_levels[$idx]}"
            break
        fi
    fi
    
    input_upper=$(echo "$input" | tr '[:lower:]' '[:upper:]')
    for level in "${valid_log_levels[@]}"; do
        if [[ "$input_upper" == "$level" ]]; then
            USER_LOG="$input_upper"
            break 2
        fi
    done
    echo "Invalid log level. Please choose from: ${valid_log_levels[*]}"
done
echo "  Result: USER_LOG=$USER_LOG"
[[ "$USER_LOG" == "ERROR" ]] && echo "  ✓ PASS" || echo "  ✗ FAIL"
echo ""

# Test 5: Invalid input should loop
echo "Test 5: Invalid input 'invalid' then 'INFO'"
USER_LOG=""
input="invalid"
loop_count=0
while true; do
    if [[ -z "$input" ]]; then
        USER_LOG="INFO"
        break
    fi
    
    if [[ "$input" =~ ^[0-9]+$ ]]; then
        idx=$((input - 1))
        if [[ $idx -ge 0 && $idx -lt ${#valid_log_levels[@]} ]]; then
            USER_LOG="${valid_log_levels[$idx]}"
            break
        fi
    fi
    
    input_upper=$(echo "$input" | tr '[:lower:]' '[:upper:]')
    for level in "${valid_log_levels[@]}"; do
        if [[ "$input_upper" == "$level" ]]; then
            USER_LOG="$input_upper"
            break 2
        fi
    done
    loop_count=$((loop_count + 1))
    if [[ $loop_count -ge 2 ]]; then
        # Simulate second input being "INFO"
        input="INFO"
        continue
    fi
    echo "Invalid log level. Please choose from: ${valid_log_levels[*]}"
done
echo "  Result: USER_LOG=$USER_LOG"
[[ "$USER_LOG" == "INFO" ]] && echo "  ✓ PASS" || echo "  ✗ FAIL"
echo ""

echo "=== All tests completed ==="
