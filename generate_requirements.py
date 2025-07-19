import subprocess

# List of packages to ignore
EXCLUDE_KEYWORDS = [
    'android', 'pygame', 'kivy', 'pyjnius', 'audiostream', 'PySDL2',
    'cmake', 'ninja', 'pybind11', 'pkgconfig', 'scikit-build', 'setuptools', 'wheel',
    'lazy-object-proxy', 'astroid', 'mccabe', 'pylint', 'parso', 'jedi', 'isort',
    'dill', 'docutils', 'platformdirs', 'tzlocal'
]

def is_valid_package(line):
    return not any(excluded in line.lower() for excluded in EXCLUDE_KEYWORDS)

def generate_clean_requirements():
    try:
        # Get all installed packages via pip freeze
        result = subprocess.run(['pip', 'freeze'], capture_output=True, text=True, check=True)
        all_packages = result.stdout.strip().split('\n')

        # Filter out excluded packages
        clean_packages = [pkg for pkg in all_packages if is_valid_package(pkg)]

        # Write to requirements.txt
        with open('requirements.txt', 'w') as f:
            f.write('\n'.join(clean_packages))

        print("✅ Clean requirements.txt created successfully.")

    except subprocess.CalledProcessError as e:
        print("❌ Error generating requirements.txt:", e)

if __name__ == '__main__':
    generate_clean_requirements()