
# CRIS Map Example:

```html
<g id="Buildings_layer" data-geometry-type="point" style="display: block;">
<circle fill="rgb(76, 230, 0)" fill-opacity="1" stroke="rgb(52, 52, 52)" stroke-opacity="1" stroke-width="1.3333333333333333" stroke-linecap="butt" stroke-linejoin="miter" stroke-miterlimit="4" cx="552" cy="253" r="6" transform="matrix(0.99984770,-0.01745241,0.01745241,0.99984770,-4.33138655,9.67226148)" fill-rule="evenodd" stroke-dasharray="none" dojoGfxStrokeStyle="solid"></circle>
```

# Workflows

## By Address

* Click Spacial Tab
* Wait for tab change
* Enter address in "Option B: Find an Address Location"
* Click "Find address" button
* Wait for map to load
* Click the circle in the middle of map
* Wait for dialog element
* Click view button
* Wait for dialog element
* Take screenshot of map
* Click "Atts" tab
* Wait for tab change
* Loop over each row
  * Click attachment button (title is "Local Server")
  * Download contents of new tab
* Click "Children" tab
* Wait for tab change
* Loop over each row
  * Click "View" icon
  * Wait for dialog element
  * Click "Inventory Form" button
  * Download contents of the new tab
  * Click "close" button

## By USN
* Enter usn into "USN Number" field
* Click "Search" button
* Wait for Results tab to load
* Click "View" button
* Wait for dialog to load
* ...see above

# ArcGIS api
* Sample API: https://data.gis.ny.gov/datasets/nysparks::building-usn-points/api
* Sample geometry extents for HRSH: -74.060,41.664,-73.765,41.754
* Spacial Reference (Sample): 4326
* Spacial Relationship: Contains

# Locations
* St Lawrence:
  * Parent USN:	St. Lawrence Psychiatric Center District (08916.000113)
  * Survey: 11SR00185