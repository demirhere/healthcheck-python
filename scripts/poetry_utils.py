import toml


def set_version():
	with open('VERSION', 'r') as f:
		version = f.read().strip()

	# Load the pyproject.toml file
	with open('pyproject.toml', 'r') as f:
		pyproject = toml.load(f)

	# Update the version
	pyproject['tool']['poetry']['version'] = version

	# Write the updated pyproject.toml file back to disk
	with open('pyproject.toml', 'w') as f:
		toml.dump(pyproject, f)

	with open("healthcheck_python/release.py", 'r') as file:
		lines = file.readlines()

	# Update the version in the lines
	updated_lines = []
	for line in lines:
		if line.startswith('__version__ ='):
			updated_lines.append(f'__version__ = \'{version}\'\n')
		else:
			updated_lines.append(line)

	# Write the updated lines back to the file
	with open("healthcheck_python/release.py", 'w') as file:
		file.writelines(updated_lines)
