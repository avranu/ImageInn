<template>
  <v-app>
    <v-app-bar color="primary">
      <v-app-bar-nav-icon @click="drawer = !drawer" v-if="!$vuetify.breakpoint.mdAndUp"></v-app-bar-nav-icon>
      <v-toolbar-title>Synctuary</v-toolbar-title>
      <v-spacer/>
      <v-breadcrumbs :items="breadcrumbs" divider="/"></v-breadcrumbs>
    </v-app-bar>
    <v-sheet class="d-flex">
      <v-navigation-drawer v-model="drawer" color="accent" :mini-variant="mini" style="height: calc(100vh - 100px); top: 64px;">
        <v-list>
          <v-list-item @click="drawer = !drawer" link v-if="!$vuetify.breakpoint.mdAndUp">
            <v-list-item-action>
              <v-icon>mdi-chevron-left</v-icon>
            </v-list-item-action>
          </v-list-item>
          <v-divider></v-divider>
          <v-list-item :to="item.to" link v-for="item in items" :key="item.title">
            <v-list-item-action>
              <v-icon>{{ item.icon }}</v-icon>
            </v-list-item-action>
            <v-list-item-content>
              <v-list-item-title>{{ item.title }}</v-list-item-title>
            </v-list-item-content>
          </v-list-item>
        </v-list>
      </v-navigation-drawer>
      <v-main>
        <v-container fluid>
          <router-view></router-view>
        </v-container>
      </v-main>
    </v-sheet>
    <v-footer color="primary">
      <span class="white--text">© 2023 Synctuary</span>
    </v-footer>
  </v-app>
</template>

<script>
export default {
  data: () => ({
    drawer: null,
    clipped: false,
    mini: false,
    breadcrumbs: [
      { text: 'Home', disabled: false, href: '/' },
    ],
    items: [
      { title: 'Home', icon: 'mdi-home', to: '/' },
      { title: 'Settings', icon: 'mdi-settings', to: '/settings' },
      { title: 'SD Cards', icon: 'mdi-sd', to: '/sd' },
      { title: 'Backup', icon: 'mdi-cloud-upload', to: '/backup' },
    ],
  }),
  created() {
    this.drawer = this.$vuetify.breakpoint.mdAndUp;
  },
}
</script>
