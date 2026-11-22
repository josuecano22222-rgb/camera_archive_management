frappe.ui.form.on("Archive Ingest Batch", {
	refresh(frm) {
		if (frm.is_new() || !["Draft", "Failed", "Queued"].includes(frm.doc.status)) return;
		frm.add_custom_button(__("Queue ingest"), () => {
			frappe.call({
				method: "camera_archive_management.api.spatial.queue_archive_ingest",
				type: "POST",
				args: { batch_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Queueing archive manifest…")
			}).then(() => frm.reload_doc());
		}, __("Archive Actions"));
	}
});
