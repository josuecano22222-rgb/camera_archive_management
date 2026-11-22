frappe.ui.form.on("Archive Asset", {
	refresh(frm) {
		if (frm.is_new() || !["Pending", "Failed", "Queued"].includes(frm.doc.index_status)) return;
		frm.add_custom_button(__("Queue indexing"), () => {
			frappe.call({
				method: "camera_archive_management.api.archive.queue_asset_index",
				type: "POST",
				args: { asset_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Queueing archive indexing…")
			}).then(() => frm.reload_doc());
		}, __("Archive Actions"));
	}
});
