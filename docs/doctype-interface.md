# DocType views and form layout

Frappe v15 supplies List, Report Builder, Dashboard, and (except for File) Kanban views through its standard List View switcher. Kanban boards are user-created and depend on a boardable Select field; this app does not seed database records or user-specific boards as fixtures.

The app enables other views only where the DocType has the data shape they need:

| DocType | Additional view(s) | Basis |
| --- | --- | --- |
| Archive Asset | Calendar, Gantt | `recorded_from` / `recorded_to` are a meaningful capture interval; the list query also loads those dates for Gantt. |
| CAM Vehicle | Image | Existing `vehicle_list_image` image field. |
| Vehicle Type | Image | Existing `vehicle_type_image` attachment. |
| Camera | Map | Existing Geolocation field and coordinate fields. |
| Camera Area | Tree | Existing nested-set hierarchy and parent field. |
| Geo Admin Area | Tree, Map | Existing nested-set hierarchy and latitude/longitude. |
| Geo Boundary | Map | Permission-filtered centroid markers using the boundary-specific centroid fields. |
| Geo Gazetteer Place | Map | Existing latitude/longitude. |
| Motion Event | Map | Permission-filtered event snapshot coordinates. |

Geo Boundary and Motion Event use a small permission-filtered adapter for their nonstandard centroid / snapshot coordinate fields; invalid or blank coordinate pairs are skipped. Motion Event is a point-in-time event with no end field; because Frappe v15 couples Calendar and Gantt availability to the same calendar configuration, it is not given a misleading editable Gantt interval.

Form fields for substantive records are grouped into workflow tabs and labeled sections. Inline child-table DocTypes remain compact so grid editing is not burdened with nested tabs. Frappe-managed nested-set maintenance fields on Camera Area and Geo Admin Area are hidden from routine form editing.
