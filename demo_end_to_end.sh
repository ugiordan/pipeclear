#!/bin/bash
# End-to-end demo showing complete RHOAI workflow

set -e  # Exit on error

echo "============================================================"
echo "RHOAI Pipeline Preflight - End-to-End Demo"
echo "============================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Demo notebooks
SIMPLE_NOTEBOOK="examples/demo_notebooks/1_simple_success.ipynb"
PROBLEM_NOTEBOOK="examples/demo_notebooks/2_resource_problem.ipynb"
KITCHEN_SINK="examples/demo_notebooks/3_kitchen_sink.ipynb"

echo -e "${BLUE}[1/5] Testing Simple Notebook (Should Pass)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python -m src.cli analyze "$SIMPLE_NOTEBOOK"
echo ""

echo -e "${YELLOW}Press Enter to continue...${NC}"
read

echo ""
echo -e "${BLUE}[2/5] Testing Notebook with Resource Problem${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python -m src.cli analyze "$PROBLEM_NOTEBOOK" || true  # Don't exit on error
echo ""

echo -e "${YELLOW}Press Enter to continue...${NC}"
read

echo ""
echo -e "${BLUE}[3/5] Testing Kitchen Sink with Time Comparison${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python -m src.cli analyze "$KITCHEN_SINK" --compare || true
echo ""

echo -e "${YELLOW}Press Enter to continue...${NC}"
read

echo ""
echo -e "${BLUE}[4/5] Generating Pipeline from Simple Notebook${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
OUTPUT_FILE="/tmp/demo_rhoai_pipeline.py"
python -m src.cli analyze "$SIMPLE_NOTEBOOK" --output "$OUTPUT_FILE"
echo ""
echo -e "${GREEN}✓ Generated pipeline:${NC}"
echo "  $(wc -l < $OUTPUT_FILE) lines of Python code"
echo ""
echo "First 25 lines:"
head -25 "$OUTPUT_FILE"
echo "..."
echo ""

echo -e "${YELLOW}Press Enter to continue...${NC}"
read

echo ""
echo -e "${BLUE}[5/5] Compiling to RHOAI-Ready YAML${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd /tmp
python "$OUTPUT_FILE"
cd - > /dev/null

YAML_FILE="/tmp/simple_notebook.yaml"
if [ -f "$YAML_FILE" ]; then
    echo -e "${GREEN}✓ Compiled to YAML successfully!${NC}"
    echo "  Size: $(ls -lh $YAML_FILE | awk '{print $5}')"
    echo ""
    echo "YAML structure (first 30 lines):"
    head -30 "$YAML_FILE"
    echo "..."
else
    echo -e "${RED}✗ YAML compilation failed${NC}"
    exit 1
fi

echo ""
echo "============================================================"
echo -e "${GREEN}✅ Demo Complete!${NC}"
echo "============================================================"
echo ""
echo "Summary:"
echo "  ✓ Validated 3 different notebooks"
echo "  ✓ Detected resource, security, and dependency issues"
echo "  ✓ Generated production-ready KFP pipeline"
echo "  ✓ Compiled to RHOAI-deployable YAML"
echo ""
echo "Next steps:"
echo "  1. Review generated files:"
echo "     - Python: $OUTPUT_FILE"
echo "     - YAML:   $YAML_FILE"
echo ""
echo "  2. Deploy to RHOAI (if you have cluster access):"
echo "     python scripts/deploy_to_rhoai.py $YAML_FILE"
echo ""
echo "  3. Or upload via RHOAI Web UI:"
echo "     Data Science Pipelines → Import pipeline → Upload $YAML_FILE"
echo ""
