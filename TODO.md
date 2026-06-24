# TODO

- Store GitHub repository immutable `id` or `node_id` in the database and models so repository renames can be detected. Keep `full_name` as display/search text, but use the immutable ID to merge renamed repositories and preserve feedback, tags, snapshots, and scoring history.
