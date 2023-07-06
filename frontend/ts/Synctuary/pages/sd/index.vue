<template>
    <v-list>
      <v-list-item v-for="sdCard in sdCards" :key="sdCard.path" @click="goToDetails(sdCard.path)">
        <v-list-item-title>{{ sdCard.path }}</v-list-item-title>
      </v-list-item>
    </v-list>
  </template>
  
  <script>
  export default {
    async asyncData({ $axios }) {
      const sdCards = await $axios.$get('/dashboard/api/sd/')
      return { sdCards }
    },
    methods: {
      goToDetails(path) {
        this.$router.push(`/dashboard/api/sd/${path}`)
      },
    },
  }
  </script>
  