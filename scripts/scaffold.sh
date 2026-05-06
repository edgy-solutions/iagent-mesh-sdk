#!/bin/bash
set -e

echo "=== iagent-mesh DevEx Scaffolder ==="
echo "Select a template:"

# Dynamically parse templates
TEMPLATES=()
i=1
for dir in ../templates/*/; do
    if [ -d "$dir" ]; then
        basename=$(basename "$dir")
        TEMPLATES+=("$basename")
        echo "$i) $basename"
        i=$((i+1))
    fi
done

read -p "Enter number: " choice
if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#TEMPLATES[@]}" ]; then
    echo "Invalid choice."
    exit 1
fi

SELECTED_TEMPLATE="${TEMPLATES[$((choice-1))]}"
TEMPLATE_DIR="../templates/$SELECTED_TEMPLATE"

read -p "Enter Tool Name (e.g., my_new_tool): " TOOL_NAME
read -p "Is this an MCP Server? (y/n) [n]: " IS_MCP
if [[ "$IS_MCP" =~ ^[Yy]$ ]]; then
    TOOL_URN="urn:li:mcpServer:$TOOL_NAME"
else
    TOOL_URN="urn:li:aitool:$TOOL_NAME"
fi
read -p "Target Directory (e.g., ./my_new_tool): " TARGET_DIR
read -p "Is 'uv' installed? (y/n): " UV_INSTALLED

mkdir -p "$TARGET_DIR"
echo "Copying template $SELECTED_TEMPLATE to $TARGET_DIR..."

# Copy files
find "$TEMPLATE_DIR" -type f -not -name "template.yaml" | while read file; do
    rel_path="${file#$TEMPLATE_DIR/}"
    dest_path="$TARGET_DIR/$rel_path"
    mkdir -p "$(dirname "$dest_path")"
    cp "$file" "$dest_path"
done

# Perform string replacements
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/REPLACE_ME_NAME/$TOOL_NAME/g" "$TARGET_DIR/pyproject.toml" "$TARGET_DIR/app.py"
else
    sed -i "s/REPLACE_ME_NAME/$TOOL_NAME/g" "$TARGET_DIR/pyproject.toml" "$TARGET_DIR/app.py"
fi

# Generate .s2i/bin/assemble
mkdir -p "$TARGET_DIR/.s2i/bin"
cat << 'EOF' > "$TARGET_DIR/.s2i/bin/assemble"
#!/bin/bash
set -e
echo "---> Installing dependencies using uv..."
pip install uv
uv pip install --system -r pyproject.toml
EOF
chmod +x "$TARGET_DIR/.s2i/bin/assemble"

# Generate Jenkinsfile
cat << EOF > "$TARGET_DIR/Jenkinsfile"
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                echo 'Building $TOOL_NAME with S2I...'
                sh 's2i build . python-39-centos7 $TOOL_NAME:latest'
            }
        }
    }
}
EOF

echo "✅ Successfully scaffolded $TOOL_NAME at $TARGET_DIR!"
